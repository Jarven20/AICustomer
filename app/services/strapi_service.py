import os
import json
import requests
import httpx
from app.core.config import settings
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from tqdm import tqdm
import time
import tempfile
import shutil
from datetime import datetime, timedelta
from app.services.cleanup import delete_update_file

class StrapiService:
    def __init__(self):
        """初始化 Strapi 服务"""
        self.base_url = settings.STRAPI_API_URL
        self.api_token = settings.STRAPI_API_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
    
        # 创建数据存储目录 - 修改为 app 目录下的 data 文件夹
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        os.chmod(self.data_dir, 0o777)
            
        # 创建 ChromaDB 数据目录
        self.chroma_db_path = os.path.join(self.data_dir, "chroma_db")
        if not os.path.exists(self.chroma_db_path):
            os.makedirs(self.chroma_db_path)
            print(f"✅ 创建 ChromaDB 数据目录: {self.chroma_db_path}")
        os.chmod(self.chroma_db_path, 0o777)
            
        # 初始化 ChromaDB
        print(f"\n🔧 初始化 ChromaDB 客户端...")
        print(f"数据目录: {self.chroma_db_path}")
        
        # 确保所有现有文件和目录都有正确的权限
        for root, dirs, files in os.walk(self.chroma_db_path):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o777)
            for f in files:
                os.chmod(os.path.join(root, f), 0o777)
        
        self.chroma_client = chromadb.PersistentClient(
            path=self.chroma_db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                persist_directory=self.chroma_db_path,
                is_persistent=True
            )
        )
        print("✅ ChromaDB 客户端初始化成功")
        
        # 初始化 OpenAI 客户端
        self.openai_api_key = settings.OPENAI_API_KEY
        if not self.openai_api_key:
            print("⚠️ 警告: 未设置 OPENAI_API_KEY 环境变量")
            
        print(f"\n🔧 OpenAI 客户端初始化:")
        print(f"OpenAI API Key 已设置: {'✅ 是' if self.openai_api_key else '❌ 否'}")
        print(f"OpenAI API URL: {settings.OPENAI_API_URL}")
        
        # 初始化 OpenAI 客户端
        self.openai_client = OpenAI(
            api_key=self.openai_api_key,
            base_url=settings.OPENAI_API_URL,
            default_headers={"x-auth-key": settings.OPENAI_AUTH_KEY},
            http_client=httpx.Client(
                verify=False  # 如果有 SSL 证书问题，可以禁用验证
            )
        )
            
        # 打印配置信息（不包含敏感信息）
        print(f"\nStrapi 服务初始化:")
        print(f"API URL: {self.base_url}")
        print(f"数据目录: {self.data_dir}")
        print(f"API Token 已设置: {'✅ 是' if self.api_token else '❌ 否'}")
        print(f"OpenAI API Key 已设置: {'✅ 是' if self.openai_api_key else '❌ 否'}")
        print(f"ChromaDB 持久化目录: {self.chroma_db_path}")
    
    def get_all_knowledge(self, endpoint="api/im-customer-service-knowledge-bases", params=None):  #当 endpoint 为空字符串时，URL 就只会使用 base_url，不会添加额外的路径
        """
        获取所有知识点数据（分页处理）  中间函数，被fetch_and_save_knowledge调用
        
        Args:
            endpoint (str): API 端点，例如 'api/knowledge-base'
            params (dict, optional): 请求参数
            
        Returns:
            list: 所有获取到的数据
        """
        if params is None:
            params = {}
        
        all_data = []
        page = 1
        page_size = 100  # 每页数据量
        total_pages = 1  # 初始值，会在第一次请求后更新
        
        while page <= total_pages:
            # 更新分页参数
            current_params = {
                **params,
                'pagination[page]': page,
                'pagination[pageSize]': page_size
            }
            
            try:
                # 构建完整的 URL，确保不会出现双斜杠
                base_url = self.base_url.rstrip('/')
                endpoint = endpoint.lstrip('/')
                url = f"{base_url}/{endpoint}"
                print(f"\n尝试连接: {url}")
                print(f"请求参数: {current_params}")
                
                # 发送请求
                response = requests.get(
                    url,
                    params=current_params,
                    headers=self.headers,
                    timeout=30,
                    verify=False  # 临时禁用 SSL 验证，用于调试
                )
                
                # 打印响应信息
                print(f"响应状态码: {response.status_code}")
                print(f"响应头: {dict(response.headers)}")
                
                response.raise_for_status()
                
                result = response.json()
                
                # 提取数据
                if 'data' in result and isinstance(result['data'], list):
                    all_data.extend(result['data'])
                    print(f"成功获取 {len(result['data'])} 条数据")
                else:
                    print("警告: 响应中没有找到 data 字段或不是列表类型")
                    print(f"响应内容: {result}")
                
                # 更新总页数
                if 'meta' in result and 'pagination' in result['meta']:
                    pagination = result['meta']['pagination']
                    total_pages = pagination.get('pageCount', 1)
                    print(f"获取第 {page}/{total_pages} 页，每页 {page_size} 条，总计 {pagination.get('total', 0)} 条数据")
                else:
                    print("警告: 响应中没有找到分页信息")
                
                page += 1
                
            except requests.exceptions.SSLError as e:
                print(f"SSL 证书验证错误: {str(e)}")
                print("请检查 API URL 是否正确，或确保服务器证书有效")
                break
            except requests.exceptions.ConnectionError as e:
                print(f"连接错误: {str(e)}")
                print("请检查:")
                print("1. Strapi 服务器是否正在运行")
                print("2. API URL 是否正确")
                print("3. 网络连接是否正常")
                break
            except requests.exceptions.Timeout as e:
                print(f"请求超时: {str(e)}")
                print("请检查网络连接或增加超时时间")
                break
            except requests.exceptions.RequestException as e:
                print(f"请求错误: {str(e)}")
                print(f"响应内容: {getattr(e.response, 'text', '无响应内容')}")
                break
            except Exception as e:
                print(f"获取数据失败（页码 {page}）: {str(e)}")
                break
        
        return all_data
    
    def save_to_json(self, data, filename):
        """
        将数据保存为 JSON 文件  中间函数，被fetch_and_save_knowledge调用
        
        Args:
            data: 要保存的数据
            filename (str): 文件名
            
        Returns:
            str: 保存的文件路径
        """
        filepath = os.path.join(self.data_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"数据已保存到: {filepath}")
        return filepath
    
    def fetch_and_save_knowledge(self, endpoint="api/im-customer-service-knowledge-bases", params=None):
        """
        获取并保存所有知识点数据  中间函数，被store_faq_in_chromadb调用
        
        Args:
            endpoint (str): API 端点
            params (dict, optional): 额外的请求参数
            
        Returns:
            str: 保存的文件路径
        """
        if params is None:
            params = {}
            
        # 添加 populate 参数以获取完整数据
        params['populate'] = '*'
        
        # 获取所有数据
        all_data = self.get_all_knowledge(endpoint, params)
        
        # 构建完整数据结构
        full_data = {
            "data": all_data,
            "meta": {
                "pagination": {
                    "page": 1,
                    "pageSize": len(all_data),
                    "pageCount": 1,
                    "total": len(all_data)
                }
            }
        }
        
        # 保存为 JSON 文件 - 使用固定的文件名
        # return self.save_to_json(full_data, f"{endpoint.replace('/', '_')}_full.json")
        return self.save_to_json(full_data, "strapi_knowledge_full.json") # <-- 修改文件名
    
    def parse_knowledge_json(self, input_file="strapi_knowledge_full.json", output_file="strapi_knowledge_parsed.json"): # <-- 修改默认文件名
        """
        解析知识库 JSON 文件，提取指定字段并生成新文件  中间函数，被store_faq_in_chromadb调用
        
        Args:
            input_file (str): 输入的 JSON 文件名
            output_file (str): 输出的 JSON 文件名
            
        Returns:
            str: 输出文件的完整路径
        """
        try:
            # 构建输入和输出文件的完整路径
            input_filepath = os.path.join(self.data_dir, input_file)
            output_filepath = os.path.join(self.data_dir, output_file)
            
            # 检查输入文件是否存在
            if not os.path.exists(input_filepath):
                raise FileNotFoundError(f"输入文件不存在: {input_filepath}")
            
            # 读取输入文件
            with open(input_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            print(f"成功读取 {len(data)} 条数据")
            
            # 提取指定字段
            parsed_data = []
            empty_faq_count = 0
            
            if 'data' in data:
                for item in data['data']:
                    attributes = item.get('attributes', {})
                    faq = attributes.get('FAQ', '')
                    
                    # 跳过FAQ为空的条目或将其标记为需要注意
                    if faq is None or faq.strip() == '':
                        empty_faq_count += 1
                        # 可以选择跳过或者保留，这里我们保留但是用空字符串
                        faq = ''
                    
                    # 提取图片URL（优先取大图）
                    app_image_url = self._extract_large_image_url(attributes.get('Response_Pic_App', {}))
                    pc_image_url = self._extract_large_image_url(attributes.get('Response_Pic_Pc', {}))
                        
                    parsed_item = {
                        'id': item.get('id'),
                        'FAQ': faq,
                        'Keywords': attributes.get('Keywords', ''),
                        'Response': attributes.get('Response', ''),  # 添加Response字段
                        'Response_Pic_App_URL': app_image_url,  # 添加移动端图片URL
                        'Response_Pic_Pc_URL': pc_image_url     # 添加PC端图片URL
                    }
                    parsed_data.append(parsed_item)
            
            # 保存解析后的数据
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(parsed_data, f, ensure_ascii=False, indent=2)
            
            print(f"成功解析数据并保存到: {output_filepath}")
            print(f"共处理 {len(parsed_data)} 条数据")
            if empty_faq_count > 0:
                print(f"⚠️ 警告: 有 {empty_faq_count} 条数据的FAQ字段为空")
            
            return output_filepath
            
        except Exception as e:
            print(f"解析 JSON 文件失败: {str(e)}")
            return None

    def get_embedding(self, text):
        """
        使用 OpenAI 获取文本的 embedding  中间函数，被store_faq_in_chromadb调用
        
        Args:
            text (str): 要获取 embedding 的文本
            
        Returns:
            list: embedding 向量
        """
        if not self.openai_api_key:
            print("❌ 错误: 未设置 OPENAI_API_KEY 环境变量")
            return None
            
        max_retries = 5  # 增加重试次数
        retry_delay = 2  # 增加初始延迟时间
        max_delay = 32   # 最大延迟时间
        
        for attempt in range(max_retries):
            try:
                print(f"📡 正在获取文本 embedding (尝试 {attempt + 1}/{max_retries})...")
                # 增加超时时间到 60 秒
                response = self.openai_client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=text,
                    timeout=5  # 设置 5 秒超时
                )
                print("✅ 成功获取 embedding")
                return response.data[0].embedding
            except Exception as e:
                error_msg = str(e)
                if "api_key" in error_msg.lower():
                    print("❌ OpenAI API Key 无效或未正确设置")
                    print("请检查 OPENAI_API_KEY 环境变量是否正确设置")
                    return None
                elif "rate limit" in error_msg.lower():
                    print("⚠️ API 调用频率超限")
                    if attempt < max_retries - 1:
                        current_delay = min(retry_delay * (2 ** attempt), max_delay)  # 指数退避，但不超过最大延迟
                        print(f"等待 {current_delay} 秒后重试...")
                        time.sleep(current_delay)
                    continue
                elif "timeout" in error_msg.lower():
                    print("⚠️ 请求超时")
                    if attempt < max_retries - 1:
                        current_delay = min(retry_delay * (2 ** attempt), max_delay)
                        print(f"等待 {current_delay} 秒后重试...")
                        time.sleep(current_delay)
                    continue
                else:
                    if attempt < max_retries - 1:
                        print(f"❌ 获取 embedding 失败 (尝试 {attempt + 1}/{max_retries})")
                        print(f"错误信息: {error_msg}")
                        current_delay = min(retry_delay * (2 ** attempt), max_delay)
                        print(f"等待 {current_delay} 秒后重试...")
                        time.sleep(current_delay)
                    else:
                        print(f"❌ 获取 embedding 最终失败")
                        print(f"错误信息: {error_msg}")
                        print("请检查:")
                        print("1. 网络连接是否正常")
                        print("2. OpenAI API 服务是否可用")
                        print("3. API Key 是否有足够的配额")
                        print("4. 是否需要使用代理服务器")
                        return None

    def store_faq_in_chromadb(self, recreate_collection=True):
        """
        将FAQ信息存储到ChromaDB  主函数，被main.py调用
        
        Args:
            recreate_collection (bool): 是否重新创建集合，默认为True
            
        Returns:
            bool: 是否成功存储
        """
        try:
            print("\n📥 开始将FAQ数据存储到ChromaDB...")
            
            # 加载解析后的知识库数据
            json_path = os.path.join(self.data_dir, "strapi_knowledge_parsed.json")
            if not os.path.exists(json_path):
                print(f"❌ 错误: 找不到知识库文件 {json_path}")
                return False
                
            with open(json_path, 'r', encoding='utf-8') as f:
                knowledge_data = json.load(f)
                
            print(f"📚 从 {json_path} 加载了 {len(knowledge_data)} 条问答数据")
            
            # 准备集合
            if recreate_collection:
                print("🗑️ 重新创建集合 'im-customer-service'...")
                # 如果集合已存在，则删除
                try:
                    self.chroma_client.delete_collection('im-customer-service')
                    print("✅ 成功删除现有集合")
                except Exception as e:
                    print(f"ℹ️ 删除集合时出现消息: {str(e)}")
                
                # 创建新集合
                collection = self.chroma_client.create_collection(
                    name='im-customer-service',
                    metadata={"description": "IM客服知识库，用于AI助手生成回答。"},
                    embedding_function=self._get_embedding_function()  # 使用自定义嵌入函数
                )
                print("✅ 成功创建新集合")
            else:
                # 获取或创建集合
                try:
                    collection = self.chroma_client.get_collection(
                        name='im-customer-service',
                        embedding_function=self._get_embedding_function()  # 使用自定义嵌入函数
                    )
                    print("✅ 成功获取现有集合")
                except Exception as e:
                    print(f"ℹ️ 获取集合时出现消息: {str(e)}")
                    collection = self.chroma_client.create_collection(
                        name='im-customer-service',
                        metadata={"description": "IM客服知识库，用于AI助手生成回答。"},
                        embedding_function=self._get_embedding_function()  # 使用自定义嵌入函数
                    )
                    print("✅ 集合不存在，已创建新集合")
            
            # 预处理数据：将知识数据转换为FAQ文本
            print("🔍 正在预处理FAQ数据...")
            texts = []      # 存储FAQ文本
            metadatas = []  # 存储元数据
            ids = []        # 存储唯一ID
            
            for item in knowledge_data:
                # 获取ID，确保为字符串类型
                item_id = str(item.get('id', ''))
                
                # 提取FAQ、关键词、回答文本
                faq = item.get('FAQ', '')
                keywords = item.get('Keywords', '')
                response = item.get('Response', '')
                
                # 记录可能的空值
                if faq is None or faq == '':
                    print(f"⚠️ 警告: ID为 {item_id} 的FAQ内容为空")
                
                # 组合为完整的FAQ文本用于向量检索
                # 注意：这里不包含Response，因为问答匹配主要基于问题和关键词
                # 但在元数据中包含了完整信息
                faq_text_list = self.preprocess_faq_text(faq)
                if not faq_text_list:  # 检查列表是否为空
                    print(f"⚠️ 警告: ID为 {item_id} 的FAQ处理后为空，跳过")
                    continue  # 跳过空内容
                
                # 将列表连接为字符串用于存储
                faq_text = "\n".join(faq_text_list)
                
                # 直接嵌入FAQ文本
                # embedding = self.get_embedding(faq_text)
                # if embedding is None:
                #     print(f"⚠️ 警告: 无法获取ID为 {item_id} 的嵌入向量，跳过")
                #     continue
                
                # 准备元数据
                metadata = {
                    "id": item_id,
                    "faq": faq if faq is not None else "",
                    "keywords": keywords if keywords is not None else "",
                    "response": response if response is not None else ""
                }
                
                texts.append(faq_text)
                metadatas.append(metadata)
                ids.append(f"faq_{item_id}")
            
            if not texts:
                print("❌ 错误: 没有有效的FAQ数据")
                return False
                
            print(f"✅ 预处理完成，共有 {len(texts)} 条FAQ数据准备加入向量数据库")
            
            # 分批处理，每批100条
            batch_size = 100
            batches = (len(texts) + batch_size - 1) // batch_size  # 向上取整
            
            for i in range(batches):
                start_idx = i * batch_size
                end_idx = min(start_idx + batch_size, len(texts))
                
                print(f"🔄 处理批次 {i+1}/{batches}，项目 {start_idx}-{end_idx-1}...")
                
                batch_texts = texts[start_idx:end_idx]
                batch_metadatas = metadatas[start_idx:end_idx]
                batch_ids = ids[start_idx:end_idx]
                
                # 添加到ChromaDB
                collection.add(
                    documents=batch_texts,
                    metadatas=batch_metadatas,
                    ids=batch_ids
                )
                
                print(f"✅ 批次 {i+1}/{batches} 处理完成")
            
            print(f"\n🎉 成功将 {len(texts)} 条FAQ数据存储到ChromaDB")
            
            # 刷新搜索提示列表
            try:
                from app.services.hint_service import hint_service
                hint_service.refresh()
                print("✅ 搜索提示列表已刷新")
            except Exception as e:
                print(f"⚠️ 刷新搜索提示列表失败: {str(e)}")
            
            return True
            
        except Exception as e:
            print(f"❌ 存储FAQ数据到ChromaDB失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def preprocess_faq_text(self, text):
        """
        预处理FAQ文本  中间函数，被store_faq_in_chromadb调用
        
        Args:
            text (str): 原始文本
            
        Returns:
            list: 处理后的文本列表
        """
        # 检查是否为None或空字符串
        if text is None or not text.strip():
            return []
            
        # 移除常见的对话词语
        stop_words = ["您好", "请问", "你好", "请", "怎么", "如何", "在哪", "哪里", "是否", "能否"]
        
        # 按换行符分割多个问题
        questions = text.split('\n')
        
        processed_questions = []
        for question in questions:
            # 移除停用词
            for word in stop_words:
                question = question.replace(word, "")
            # 移除多余空格
            question = " ".join(question.split())
            if question:  # 如果处理后的问题不为空
                processed_questions.append(question)
        
        return processed_questions

    def calculate_keyword_similarity(self, query, keywords):
        """
        计算关键词相似度  中间函数，被search_similar_faqs调用
        
        Args:
            query (str): 查询文本
            keywords (str): 关键词字符串
            
        Returns:
            float: 相似度分数 (0-1)
        """
        if not keywords:
            return 0.0
            
        # 将关键词字符串分割成列表
        keyword_list = keywords.split()
        
        # 计算查询中包含多少个关键词
        matches = sum(1 for keyword in keyword_list if keyword in query)
        
        # 返回匹配比例
        return matches / len(keyword_list) if keyword_list else 0.0

    def search_similar_faqs(self, query, n_results=3):
        """
        搜索与查询相似的问题  中间函数，被get_similar_faq_ids调用
        
        Args:
            query (str): 查询文本
            n_results (int): 返回结果数量
            
        Returns:
            list: 相似问题列表
        """
        try:
            print(f"\n开始搜索: {query}")
            
            # 定义正确的集合名称
            collection_name = "im-customer-service"
            
            # 检查集合是否存在
            collections = self.chroma_client.list_collections()
            print(f"当前可用的集合: {[c.name for c in collections]}")
            
            # 检查集合名称是否在可用集合列表中
            if not any(c.name == collection_name for c in collections):
                print(f"❌ 错误: 找不到名为 '{collection_name}' 的集合")
                print("请确保已经运行过 store_faq_in_chromadb() 来初始化数据")
                return []
            
            try:
                # 获取集合
                collection = self.chroma_client.get_collection(collection_name)
                print(f"✅ 成功获取 {collection_name} 集合")
            except Exception as e:
                print(f"❌ 获取集合失败: {str(e)}")
                print("请确保已经运行过 store_faq_in_chromadb() 来初始化数据")
                return []
            
            # 检查集合是否为空
            collection_count = collection.count()
            if collection_count == 0:
                print("⚠️ 警告: 集合为空，没有可搜索的数据")
                return []
            
            print(f"集合中包含 {collection_count} 条数据")
            
            # 预处理查询文本
            processed_queries = self.preprocess_faq_text(query)
            if not processed_queries:
                print("⚠️ 警告: 查询文本预处理后为空")
                return []
                
            processed_query = processed_queries[0]  # 防止索引越界
            print(f"处理后的查询: {processed_query}")
            
            # 获取查询文本的 embedding
            print("获取查询文本的 embedding...")
            query_embedding = self.get_embedding(processed_query)
            if not query_embedding:
                print("❌ 错误: 无法获取查询文本的 embedding")
                return []
            
            # 搜索相似问题，获取更多结果用于重新排序
            print("在 ChromaDB 中搜索相似问题...")
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results * 2, collection_count)  # 确保不超过集合中的数据数量
            )
            
            # 检查结果是否为空
            if not results or 'documents' not in results or not results['documents'] or len(results['documents'][0]) == 0:
                print("⚠️ 警告: 未找到任何相似问题")
                return []
                
            # 结合向量相似度和关键词匹配重新排序
            similar_faqs = []
            for i in range(len(results['documents'][0])):
                try:
                    # 获取原始FAQ文本
                    faq_text = results['documents'][0][i]
                    
                    # 检查元数据是否存在
                    if 'metadatas' not in results or not results['metadatas'] or len(results['metadatas'][0]) <= i:
                        print(f"⚠️ 警告: 索引 {i} 的元数据不存在")
                        continue
                        
                    # 检查距离是否存在
                    if 'distances' not in results or not results['distances'] or len(results['distances'][0]) <= i:
                        print(f"⚠️ 警告: 索引 {i} 的距离不存在")
                        continue
                    
                    # 预处理FAQ文本
                    processed_faqs = self.preprocess_faq_text(faq_text)
                    if not processed_faqs:
                        processed_faqs = [faq_text]  # 如果预处理后为空，使用原始文本
                    
                    # 计算最佳匹配的FAQ文本的相似度
                    best_semantic_score = results['distances'][0][i]  # 较小的距离表示更相似
                    
                    # 检查关键词字段是否存在
                    keywords = results['metadatas'][0][i].get('keywords', '')
                    
                    # 计算关键词匹配分数
                    keyword_score = self.calculate_keyword_similarity(
                        processed_query,
                        keywords
                    )
                    
                    # 检查ID字段是否存在
                    if 'id' not in results['metadatas'][0][i]:
                        print(f"⚠️ 警告: 索引 {i} 的元数据中没有ID字段")
                        continue
                    
                    # 综合得分 (将距离转换为相似度分数，并与关键词得分结合)
                    combined_score = (1 - best_semantic_score) * 0.7 + keyword_score * 0.3
                    
                    similar_faqs.append({
                        'id': results['metadatas'][0][i]['id'],
                        'faq': faq_text,
                        'keywords': keywords,
                        'distance': best_semantic_score,
                        'keyword_score': keyword_score,
                        'combined_score': combined_score
                    })
                except Exception as e:
                    print(f"❌ 处理索引 {i} 的结果时出错: {str(e)}")
                    continue
            
            # 检查是否有有效结果
            if not similar_faqs:
                print("⚠️ 警告: 处理后没有有效的相似问题")
                return []
                
            # 根据综合得分重新排序
            similar_faqs.sort(key=lambda x: x['combined_score'], reverse=True)
            
            # 只返回请求的数量
            similar_faqs = similar_faqs[:n_results]
            
            print(f"✅ 找到 {len(similar_faqs)} 个相似问题")
            return similar_faqs
            
        except Exception as e:
            print(f"❌ 搜索相似问题失败: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印完整的堆栈跟踪
            print("请检查:")
            print("1. ChromaDB 服务是否正常运行")
            print("2. 数据库文件权限是否正确")
            print("3. 是否已经成功导入数据")
            return []

    def get_similar_faq_ids(self, query, n_results=3):
        """
        获取与查询相似的问题ID列表，按综合得分从高到低排序  中间函数，被get_faq_details_by_ids调用
        
        Args:
            query (str): 查询文本
            n_results (int): 返回结果数量
            
        Returns:
            list: 相似问题ID列表
        """
        try:
            # 获取相似问题
            similar_faqs = self.search_similar_faqs(query, n_results)
            
            # 提取ID并按综合得分排序
            faq_ids = [faq['id'] for faq in similar_faqs]
            
            print(f"\n提取到 {len(faq_ids)} 个相似问题ID:")
            for i, faq_id in enumerate(faq_ids, 1):
                print(f"{i}. ID: {faq_id}")
            return faq_ids
            
        except Exception as e:
            print(f"❌ 提取相似问题ID失败: {str(e)}")
            return []

    def get_faq_details_by_ids(self, faq_ids):
        """
        根据FAQ ID列表获取完整的知识库数据  中间函数，被format_faq_for_rag调用
        
        Args:
            faq_ids (list): FAQ ID列表
            
        Returns:
            list: 包含完整FAQ数据的列表
        """
        try:
            print(f"\n🔍 开始获取FAQ详细信息...")
            
            # 构建知识库JSON文件路径
            json_path = os.path.join(self.data_dir, "strapi_knowledge_parsed.json")
            
            # 检查解析后的文件是否存在
            if not os.path.exists(json_path):
                print(f"❌ 错误: 找不到知识库文件 {json_path}")
                return []
            
            # 读取知识库数据
            with open(json_path, 'r', encoding='utf-8') as f:
                knowledge_items = json.load(f)
            
            # 由于现在strapi_knowledge_parsed.json直接是数组格式，不需要检查格式
            if not isinstance(knowledge_items, list):
                print("❌ 错误: 知识库数据格式不正确，应为数组格式")
                return []
            
            print(f"✅ 成功加载 {len(knowledge_items)} 条知识库数据")
            
            # 创建ID到数据的映射
            id_to_data = {}
            for item in knowledge_items:
                if isinstance(item, dict) and 'id' in item:
                    item_id = str(item['id'])
                    id_to_data[item_id] = item
            
            # 获取指定ID的数据
            faq_details = []
            for faq_id in faq_ids:
                faq_id_str = str(faq_id)
                if faq_id_str in id_to_data:
                    faq_details.append(id_to_data[faq_id_str])
                else:
                    print(f"⚠️ 警告: 未找到ID为 {faq_id} 的FAQ数据")
            
            # 打印结果
            print(f"\n✅ 成功获取 {len(faq_details)} 条FAQ详细信息:")
            for i, faq in enumerate(faq_details, 1):
                print(f"\n{i}. ID: {faq.get('id')}")
                print(f"   FAQ: {faq.get('FAQ', '')[:50]}...")
                print(f"   Response: {faq.get('Response', '')[:50]}...")
                print(f"   Keywords: {faq.get('Keywords', '')}")
                print(f"   移动端图片: {'✅' if faq.get('Response_Pic_App_URL') else '❌'}")
                print(f"   PC端图片: {'✅' if faq.get('Response_Pic_Pc_URL') else '❌'}")
            
            return faq_details
                
        except Exception as e:
            print(f"❌ 获取FAQ详细信息失败: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印详细的堆栈跟踪
            return []

    def format_faq_for_rag(self, faq_details, query=None):
        """
        将FAQ详细信息格式化为适合RAG的文本格式
        
        Args:
            faq_details (list): FAQ详细信息列表
            query (str, optional): 用户查询
            
        Returns:
            str: 格式化后的文本
        """
        try:
            print("\n📝 开始格式化FAQ信息为RAG文本...")
            
            # 构建文本
            formatted_text = []
            
            # 添加语料库知识
            formatted_text.append("【语料库知识】")
            for i, faq in enumerate(faq_details, 1):
                # 提取关键字段，直接从顶级对象获取
                question = faq.get('FAQ', '')
                response = faq.get('Response', '')
                keywords = faq.get('Keywords', '')
                
                # 直接从解析后的数据中获取图片URL
                app_image_url = faq.get('Response_Pic_App_URL', '')
                pc_image_url = faq.get('Response_Pic_Pc_URL', '')
                
                # 打印出所有获取到的字段以便调试
                print(f"\nFAQ {i} 字段:")
                print(f"问题: {question}")
                print(f"回答: {response}")
                print(f"关键词: {keywords}")
                print(f"APP图片: {app_image_url}")
                print(f"PC图片: {pc_image_url}")
                
                # 格式化每个FAQ条目
                faq_text = f"FAQ {i}:\n"
                faq_text += f"问题: {question}\n"
                faq_text += f"回答: {response}\n"
                if keywords:
                    faq_text += f"关键词: {keywords}\n"
                
                # 添加图片URL（如果存在）
                if app_image_url:
                    faq_text += f"APP端图片: {app_image_url}\n"
                if pc_image_url:
                    faq_text += f"PC端图片: {pc_image_url}\n"
                
                faq_text += "-" * 50  # 分隔线
                
                formatted_text.append(faq_text)
                   
            # 合并所有文本
            result = "\n".join(formatted_text)
            
            print("✅ FAQ信息格式化完成")
            return result
            
        except Exception as e:
            print(f"❌ 格式化FAQ信息失败: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印详细的堆栈跟踪
            return ""
    
    def _extract_large_image_url(self, pic_data):
        """
        从图片数据中提取大图URL  中间函数，被format_faq_for_rag调用
        
        Args:
            pic_data (dict): 图片数据字典
            
        Returns:
            str: 大图URL，如果不存在则返回空字符串
        """
        try:
            # 检查pic_data是否包含必要的结构
            if not pic_data or 'data' not in pic_data or not pic_data['data']:
                return ""
                
            # 获取图片属性
            attributes = pic_data['data'].get('attributes', {})
            
            # 获取formats
            formats = attributes.get('formats', {})
            
            # 尝试获取大图URL
            if 'large' in formats and 'url' in formats['large']:
                return formats['large']['url']
            
            # 如果没有large格式，尝试获取其他格式
            for format_type in ['medium', 'small', 'thumbnail']:
                if format_type in formats and 'url' in formats[format_type]:
                    return formats[format_type]['url']
            
            # 如果formats中没有任何格式，尝试从原始图片获取URL
            if 'url' in attributes:
                return attributes['url']
                
            return ""
        except Exception as e:
            print(f"⚠️ 提取图片URL失败: {str(e)}")
            return ""

    def inspect_chromadb(self):
        """
        检查 ChromaDB 的数据存储情况  被main.py调用
        
        Returns:
            dict: 包含 ChromaDB 状态信息的字典
        """
        try:
            print("\n🔍 开始检查 ChromaDB 状态...")
            
            # 检查数据目录
            db_path = os.path.join(self.data_dir, "chroma_db")
            db_size = 0
            if os.path.exists(db_path):
                for root, dirs, files in os.walk(db_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        db_size += os.path.getsize(file_path)
            
            # 转换数据库大小为可读格式
            size_str = f"{db_size / (1024*1024):.2f} MB" if db_size > 1024*1024 else f"{db_size / 1024:.2f} KB"
            
            # 获取所有集合
            collections = self.chroma_client.list_collections()
            print(f"\n📚 当前可用的集合: {[c.name for c in collections]}")
            
            if not collections:
                print("⚠️ 警告: 没有找到任何集合")
                return {
                    "status": "empty",
                    "collections": [],
                    "db_path": db_path,
                    "db_size": db_size,
                    "db_size_readable": size_str
                }
            
            # 收集每个集合的信息
            collections_info = []
            for collection in collections:
                try:
                    # 获取集合中的数据条数
                    count = collection.count()
                    
                    # 获取集合的元数据
                    metadata = collection.metadata
                    
                    # 获取集合的维度（如果可用）
                    dimension = None
                    try:
                        # 尝试获取一条数据来查看维度
                        peek = collection.peek()
                        if peek and 'embeddings' in peek and len(peek['embeddings']) > 0:
                            dimension = len(peek['embeddings'][0])
                    except:
                        pass
                    
                    collection_info = {
                        "name": collection.name,
                        "count": count,
                        "dimension": dimension,
                        "metadata": metadata
                    }
                    collections_info.append(collection_info)
                    
                    # 打印集合信息
                    print(f"\n📊 集合 '{collection.name}' 信息:")
                    print(f"- 数据条数: {count}")
                    if dimension:
                        print(f"- 向量维度: {dimension}")
                    print(f"- 元数据: {metadata}")
                    
                except Exception as e:
                    print(f"❌ 获取集合 '{collection.name}' 信息失败: {str(e)}")
                    collections_info.append({
                        "name": collection.name,
                        "error": str(e)
                    })
            
            print(f"\n💾 数据库存储信息:")
            print(f"- 存储路径: {db_path}")
            print(f"- 总大小: {size_str}")
            
            return {
                "status": "success",
                "collections": collections_info,
                "db_path": db_path,
                "db_size": db_size,
                "db_size_readable": size_str
            }
            
        except Exception as e:
            print(f"\n❌ 检查 ChromaDB 状态失败: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "collections": [],
                "db_path": os.path.join(self.data_dir, "chroma_db"),
                "db_size": 0,
                "db_size_readable": "0 KB"
            }
            
    def update_knowledge_with_responses(self):
        """
        更新知识库文件，为所有条目添加空的Response字段
        
        Returns:
            bool: 操作是否成功
        """
        try:
            print("\n🔧 开始更新知识库文件，添加Response字段...")
            
            # 构建知识库文件路径
            json_path = os.path.join(self.data_dir, "strapi_knowledge_parsed.json")
            if not os.path.exists(json_path):
                print(f"❌ 错误: 找不到知识库文件 {json_path}")
                return False
                
            # 读取现有知识库数据
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            print(f"✅ 成功读取 {len(data)} 条数据")
            
            # 为每条数据添加Response字段（如果尚不存在）
            updated_count = 0
            for item in data:
                if 'Response' not in item:
                    item['Response'] = ""  # 添加空的Response字段
                    updated_count += 1
            
            # 保存更新后的数据
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            print(f"✅ 成功更新知识库文件")
            print(f"- 总条目数: {len(data)}")
            print(f"- 更新条目数: {updated_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ 更新知识库文件失败: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印详细的堆栈跟踪
            return False

    def get_recently_updated_knowledge(self, endpoint="api/im-customer-service-knowledge-bases", hours=1, params=None):
        """
        获取最近更新的知识点数据（增量更新）
        
        Args:
            endpoint (str): API 端点
            hours (int): 获取多少小时内更新的数据
            params (dict, optional): 请求参数
            
        Returns:
            list: 最近更新的数据
        """
        if params is None:
            params = {}
            
        # 计算查询时间范围
        now = datetime.now()
        update_after = now - timedelta(hours=hours)
        update_after_str = update_after.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        # 添加时间过滤器和 populate 参数
        filter_params = {
            'populate': '*',
            'filters[updatedAt][$gt]': update_after_str
        }
        
        # 合并参数
        query_params = {**params, **filter_params}
        
        # 获取满足条件的数据
        recent_data = self.get_all_knowledge(endpoint, query_params)
        
        if recent_data:
            print(f"✅ 发现 {len(recent_data)} 条最近 {hours} 小时内更新的数据")
        else:
            print(f"ℹ️ 没有发现最近 {hours} 小时内更新的数据")
            
        return recent_data
    
    def fetch_and_save_updated_knowledge(self, endpoint="api/im-customer-service-knowledge-bases", hours=1, params=None):
        """
        获取并保存最近更新的知识点数据
        
        Args:
            endpoint (str): API 端点
            hours (int): 获取多少小时内更新的数据
            params (dict, optional): 额外的请求参数
            
        Returns:
            tuple: (有更新, 文件路径) - 是否有更新的数据和保存的文件路径
        """
        if params is None:
            params = {}
            
        # 获取最近更新的数据
        recent_data = self.get_recently_updated_knowledge(endpoint, hours, params)
        
        if not recent_data:
            # 没有更新的数据，直接返回
            return False, None
            
        # 构建完整数据结构
        update_data = {
            "data": recent_data,
            "meta": {
                "pagination": {
                    "page": 1,
                    "pageSize": len(recent_data),
                    "pageCount": 1,
                    "total": len(recent_data)
                }
            }
        }
        
        # 保存为 JSON 文件 - 使用时间戳避免文件名冲突
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{endpoint.replace('/', '_')}_update_{timestamp}.json"
        filepath = self.save_to_json(update_data, output_file)
        
        print(f"✅ 新增/更新的数据已保存到: {filepath}")
        return True, filepath
    
    def update_chromadb_with_new_data(self, input_file, recreate_collection=False):
        """
        使用新增/更新的数据更新ChromaDB
        
        Args:
            input_file (str): 输入的更新数据JSON文件路径
            recreate_collection (bool): 是否重新创建集合
            
        Returns:
            bool: 是否成功更新
        """
        try:
            if recreate_collection:
                # 如果选择重建集合，直接使用现有的全量更新方法
                return self.store_faq_in_chromadb(recreate_collection=True)

            # 从JSON文件读取更新数据
            input_path = input_file if os.path.isabs(input_file) else os.path.join(self.data_dir, input_file)

            with open(input_path, 'r', encoding='utf-8') as f:
                update_data = json.load(f)

            # 解析数据 - 修改为处理 FAQ/Response 结构
            faqs_to_update = []
            if 'data' in update_data and isinstance(update_data['data'], list):
                for item in update_data['data']:
                    item_id = str(item.get('id', ''))
                    if not item_id:
                        print(f"⚠️ 跳过没有ID的更新记录")
                        continue

                    if 'attributes' in item:
                        faq = item['attributes'].get('FAQ', '')
                        keywords = item['attributes'].get('Keywords', '')
                        response = item['attributes'].get('Response', '')

                        # 至少需要 FAQ 内容才能更新向量库
                        if faq:
                            # 使用与 store_faq_in_chromadb 类似的预处理和文档构建
                            faq_text_list = self.preprocess_faq_text(faq)
                            if not faq_text_list:
                                print(f"⚠️ 警告: ID为 {item_id} 的更新FAQ处理后为空，跳过")
                                continue
                            faq_text = "\n".join(faq_text_list)

                            metadata = {
                                "id": item_id,
                                "faq": faq if faq is not None else "",
                                "keywords": keywords if keywords is not None else "",
                                "response": response if response is not None else ""
                            }

                            faqs_to_update.append({
                                'id': f"faq_{item_id}", # 使用与 store_faq_in_chromadb 一致的ID格式
                                'document': faq_text,
                                'metadata': metadata
                            })
                        else:
                             print(f"⚠️ 警告: ID为 {item_id} 的更新记录缺少FAQ内容，跳过")

            if not faqs_to_update:
                print("没有可更新的FAQ内容") # 修改日志消息
                return False

            print(f"解析得到 {len(faqs_to_update)} 条待更新的FAQ")

            # 获取或创建集合
            collection_name = "im-customer-service"
            try:
                collection = self.chroma_client.get_collection(
                    name=collection_name,
                    embedding_function=self._get_embedding_function() # 确保使用嵌入函数
                )
                print(f"获取到已存在的集合: {collection_name}")
            except Exception as e:
                print(f"获取集合时出错，尝试创建: {str(e)}")
                collection = self.chroma_client.create_collection(
                    name=collection_name,
                    embedding_function=self._get_embedding_function()
                )
                print(f"创建新集合: {collection_name}")

            # 嵌入并更新数据
            successful_updates = 0
            ids_to_upsert = [faq['id'] for faq in faqs_to_update]
            documents_to_upsert = [faq['document'] for faq in faqs_to_update]
            metadatas_to_upsert = [faq['metadata'] for faq in faqs_to_update]

            # 使用 upsert 进行更新或添加
            try:
                collection.upsert(
                    ids=ids_to_upsert,
                    documents=documents_to_upsert,
                    metadatas=metadatas_to_upsert
                )
                successful_updates = len(faqs_to_update)
                print(f"✅ 成功更新/添加 {successful_updates} 条FAQ到 ChromaDB")
            except Exception as e:
                print(f"❌ 更新/添加 ChromaDB 时出错: {str(e)}")
                # 可以在这里添加更详细的错误处理或重试逻辑

            return successful_updates > 0

        except Exception as e:
            print(f"❌ 更新 ChromaDB 失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def incremental_update_knowledge_base(self, hours=1):
        """
        增量更新知识库
        
        Args:
            hours (int): 获取多少小时内更新的数据
            
        Returns:
            bool: 是否成功更新
        """
        try:
            print(f"开始增量更新知识库（获取最近 {hours} 小时的更新）...")
            
            # 1. 获取最近更新的数据
            has_updates, update_file = self.fetch_and_save_updated_knowledge(  #返回新存的json文件路径
                endpoint="api/im-customer-service-knowledge-bases", 
                hours=hours
            )
            
            if not has_updates:
                print("没有新的更新数据，无需更新向量数据库")
                return False
                
            # 2. 更新向量数据库
            updated = self.update_chromadb_with_new_data(update_file)
            
            if updated:
                print("✅ 知识库增量更新成功")
                
                # 3. 更新主知识库文件 (strapi_knowledge_parsed.json)
                kb_updated_success = False # Flag to track if KB file update was successful
                try:
                    # 调用 update_knowledge_base_file 使用临时 update 文件更新主文件
                    kb_updated = self.update_knowledge_base_file(update_file) # <--- 更新主知识库文件
                    if kb_updated:
                        print("✅ 主知识库文件已更新")
                        kb_updated_success = True
                    else:
                        print("⚠️ 主知识库文件更新失败")
                except Exception as e:
                    print(f"⚠️ 更新主知识库文件失败: {str(e)}")

                # 4. 如果主知识库文件更新成功，则重新生成并加载搜索提示
                if kb_updated_success:
                    try:
                        from app.services.hint_service import hint_service
                        # hint_service.refresh() # <--- 不再调用 refresh
                        if hint_service.generate_and_load_hints(): # <-- 调用 generate_and_load_hints
                            print(f"✅ 已根据更新后的知识库重新生成并加载了 {len(hint_service.hint_list)} 条搜索提示。")
                        else:
                             print("❌ 重新生成搜索提示失败。")
                    except Exception as e:
                        print(f"⚠️ 重新生成搜索提示列表失败: {str(e)}")
                else:
                    print("ℹ️ 由于主知识库文件更新失败，跳过搜索提示生成步骤。")
            else:
                print("❌ 知识库增量更新失败或无更新")
            
            # 5. 清理临时文件
            try:
                delete_update_file(update_file, self.data_dir)
            except Exception as e:
                print(f"⚠️ 删除临时文件时出错: {str(e)}")
            
            return updated
            
        except Exception as e:
            print(f"❌ 增量更新知识库失败: {str(e)}")
            return False

    def update_knowledge_base_file(self, new_data_file):
        """
        使用增量更新数据更新主知识库文件
        
        Args:
            new_data_file (str): 新增数据文件路径
            
        Returns:
            bool: 是否成功更新
        """
        try:
            print(f"🔄 开始更新主知识库文件...")
            
            # 主知识库文件路径
            main_knowledge_file = os.path.join(self.data_dir, "strapi_knowledge_parsed.json")
            
            # 检查主知识库文件是否存在
            if not os.path.exists(main_knowledge_file):
                print(f"⚠️ 主知识库文件不存在: {main_knowledge_file}")
                # 如果不存在，尝试从full文件解析
                try:
                    full_file_path = os.path.join(self.data_dir, "strapi_knowledge_full.json")
                    if os.path.exists(full_file_path):
                        print(f"尝试解析全量文件: {full_file_path}")
                        self.parse_knowledge_json()
                    else:
                        print(f"❌ 找不到全量知识库文件: {full_file_path}")
                        return False
                except Exception as e:
                    print(f"❌ 解析全量文件失败: {str(e)}")
                    return False
            
            # 再次检查主知识库文件是否存在
            if not os.path.exists(main_knowledge_file):
                print(f"❌ 无法创建主知识库文件")
                return False
        
            # 读取主知识库文件
            with open(main_knowledge_file, 'r', encoding='utf-8') as f:
                main_data = json.load(f)
        
            print(f"📚 从主知识库加载了 {len(main_data)} 条记录")
        
            # 读取新增数据文件
            new_data_path = new_data_file if os.path.isabs(new_data_file) else os.path.join(self.data_dir, new_data_file)
            with open(new_data_path, 'r', encoding='utf-8') as f:
                new_data_full = json.load(f)
        
            # 确保新数据是正确格式
            new_items = []
            if 'data' in new_data_full and isinstance(new_data_full['data'], list):
                new_items = new_data_full['data']
            else:
                print(f"❌ 新增数据文件格式不正确")
                return False
            
            print(f"�� 从增量文件加载了 {len(new_items)} 条记录")
        
            # 创建ID到数据的映射，便于快速查找和更新
            id_to_index = {}
            for i, item in enumerate(main_data):
                if 'id' in item:
                    id_to_index[str(item['id'])] = i
        
            # 处理新增/更新的记录
            updated_count = 0
            new_count = 0
        
            for item in new_items:
                item_id = str(item.get('id'))
                
                if not item_id:
                    print(f"⚠️ 跳过没有ID的记录")
                    continue
                
                # 转换数据格式
                attributes = item.get('attributes', {})
                faq = attributes.get('FAQ', '')
                
                parsed_item = {
                    'id': item_id,
                    'FAQ': faq if faq is not None else '',
                    'Keywords': attributes.get('Keywords', ''),
                    'Response': attributes.get('Response', '')
                }
                
                # 检查是否存在，如果存在则更新，否则添加
                if item_id in id_to_index:
                    main_data[id_to_index[item_id]] = parsed_item
                    updated_count += 1
                else:
                    main_data.append(parsed_item)
                    id_to_index[item_id] = len(main_data) - 1
                    new_count += 1
        
            # 保存更新后的主知识库文件
            with open(main_knowledge_file, 'w', encoding='utf-8') as f:
                json.dump(main_data, f, ensure_ascii=False, indent=2)
        
            print(f"✅ 知识库文件更新成功: 更新 {updated_count} 条, 新增 {new_count} 条")
            return True
        
        except Exception as e:
            print(f"❌ 更新知识库文件失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def submit_feedback(self, feedback_id, good_or_bad, session_history, session_id):
        """
        提交用户反馈到Strapi
        
        Args:
            feedback_id (str): 反馈唯一标识符
            good_or_bad (bool): 用户是否满意回答
            session_history (list): 会话历史记录
            session_id (str): 会话ID
            
        Returns:
            tuple: (bool, str) - 成功状态和消息
        """
        try:
            # 使用本地Strapi URL和认证令牌
            local_strapi_url = settings.LOCAL_STRAPI_API_URL.rstrip('/')
            local_strapi_token = settings.LOCAL_STRAPI_API_TOKEN
            
            # 本地Strapi的请求头
            local_headers = {
                "Authorization": f"Bearer {local_strapi_token}",
                "Content-Type": "application/json"
            }
            
            endpoint = "api/ai-support-session-feedbacks"
            url = f"{local_strapi_url}/{endpoint}"
            
            # 记录接收到的会话历史信息
            print(f"\n📋 在strapi_service中收到的会话历史:")
            print(f"类型: {type(session_history)}")
            if isinstance(session_history, str):
                print(f"已是JSON字符串，长度: {len(session_history)}")
                session_history_str = session_history
            else:
                print(f"Python对象，长度: {len(session_history) if hasattr(session_history, '__len__') else 'N/A'}")
                session_history_str = json.dumps(session_history)
            
            # 构建反馈数据
            feedback_data = {
                "data": {
                    "feedback_id": feedback_id,
                    "good_or_bad": good_or_bad,
                    "session_history": session_history_str,
                    "session_id": session_id
                }
            }
            
            print(f"\n📤 提交反馈到本地Strapi: {url}")
            print(f"反馈数据: {feedback_data}")
            print(f"请求头: {local_headers}")
            
            # 发送POST请求到Strapi，使用本地认证令牌
            response = requests.post(
                url,
                json=feedback_data,
                headers=local_headers,
                timeout=10
            )
            
            # 打印完整的响应内容以便调试
            print(f"响应状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            
            # 检查响应状态
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            print(f"✅ 反馈提交成功: {result}")
            return True, "反馈提交成功"
            
        except requests.exceptions.RequestException as e:
            error_message = f"提交反馈失败: {str(e)}"
            if hasattr(e, 'response') and e.response:
                error_message += f" - 响应状态码: {e.response.status_code}, 响应内容: {e.response.text}"
            print(f"❌ {error_message}")
            return False, error_message
        except Exception as e:
            error_message = f"提交反馈失败: {str(e)}"
            print(f"❌ {error_message}")
            return False, error_message

    def _get_embedding_function(self):
        """
        获取使用 OpenAI 的 embedding 函数
        
        Returns:
            callable: 用于嵌入的函数
        """
        print("创建 OpenAI 嵌入函数...")
        
        class OpenAIEmbeddingFunction:
            def __init__(self, parent):
                self.parent = parent
                self.openai_client = parent.openai_client
                # 添加简单的内存缓存，避免重复处理相同文本
                self.cache = {}
                # 导入线程池
                from concurrent.futures import ThreadPoolExecutor
                # 减少工作线程数以提高稳定性
                self.executor = ThreadPoolExecutor(max_workers=4) # 从8减少回4
                
            def process_batch(self, batch):
                """处理单个批次的文本"""
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        start_time = time.time()
                        response = self.openai_client.embeddings.create(
                            model="text-embedding-ada-002",
                            input=batch,
                            timeout=5  # 减少超时时间到5秒
                        )
                        embeddings = [item.embedding for item in response.data]
                        processing_time = time.time() - start_time
                        print(f"✅ 批次处理完成，耗时: {processing_time:.2f}秒")
                        return embeddings
                    except Exception as e:
                        # 检查是否是超时错误
                        if "timeout" in str(e).lower() and retry < max_retries - 1:
                            wait_time = (retry + 1) * 5  # 逐步增加等待时间
                            print(f"⚠️ 批次处理超时 (尝试 {retry+1}/{max_retries})，等待 {wait_time} 秒后重试...")
                            time.sleep(wait_time)
                        else:
                            print(f"❌ 批次处理失败: {str(e)}")
                            # 返回零向量作为替代
                            return [[0.0] * 1536 for _ in batch]
                return [[0.0] * 1536 for _ in batch]  # 所有重试都失败时返回零向量

            def __call__(self, input):
                """
                使用 OpenAI API 生成文本嵌入
                
                Args:
                    input: 要嵌入的文本列表
                
                Returns:
                    list: 嵌入向量列表
                """
                if not input:
                    print("没有输入文本，返回空列表")
                    return []
                    
                print(f"使用 OpenAI API 生成 {len(input)} 个文本的嵌入向量...")
                
                # 批处理，尝试折中大小以平衡速度和稳定性
                batch_size = 50  # 从100减少到50
                all_embeddings = [None] * len(input)  # 预先分配结果空间
                
                # 对文本进行去重处理，避免重复调用API
                unique_texts = {}
                for i, text in enumerate(input):
                    if text in self.cache:
                        # 如果已经在缓存中，直接使用
                        all_embeddings[i] = self.cache[text]
                    elif text in unique_texts:
                        # 如果当前批次中已有相同文本
                        unique_texts[text].append(i)
                    else:
                        # 新文本
                        unique_texts[text] = [i]
                
                # 过滤出需要处理的新文本
                texts_to_process = list(unique_texts.keys())
                if not texts_to_process:
                    print("所有文本都在缓存中，无需调用API")
                    return all_embeddings
                
                print(f"去重后需要处理 {len(texts_to_process)} 个唯一文本")
                
                try:
                    # 分批处理
                    futures = []
                    for i in range(0, len(texts_to_process), batch_size):
                        batch = texts_to_process[i:i+batch_size]
                        batch_num = i//batch_size + 1
                        total_batches = (len(texts_to_process)-1)//batch_size + 1
                        print(f"提交批次 {batch_num}/{total_batches}，文本数量：{len(batch)}")
                        
                        # 并行提交处理任务
                        future = self.executor.submit(self.process_batch, batch)
                        futures.append((future, batch))
                    
                    # 收集并处理结果
                    for (future, batch) in futures:
                        try:
                            # 增加等待线程结果的超时时间
                            batch_embeddings = future.result(timeout=10)  # 从75秒减少到10秒
                            # 将结果保存到缓存和最终结果
                            for text, embedding in zip(batch, batch_embeddings):
                                self.cache[text] = embedding
                                # 将结果分配到对应位置
                                for idx in unique_texts[text]:
                                    all_embeddings[idx] = embedding
                        except Exception as e:
                            print(f"获取批次结果失败: {str(e)}")
                            # 对失败的批次使用零向量
                            for text in batch:
                                zero_vector = [0.0] * 1536
                                self.cache[text] = zero_vector
                                for idx in unique_texts[text]:
                                    all_embeddings[idx] = zero_vector
                    
                    # 确保所有嵌入都已生成
                    for i, embedding in enumerate(all_embeddings):
                        if embedding is None:
                            print(f"警告: 索引 {i} 的嵌入未生成，使用零向量")
                            all_embeddings[i] = [0.0] * 1536
                    
                    print(f"✅ 成功生成 {len(all_embeddings)} 个嵌入向量")
                    return all_embeddings
                    
                except Exception as e:
                    print(f"❌ 嵌入生成过程失败: {str(e)}")
                    print("返回零向量作为备选方案")
                    # 出错时返回零向量作为备选方案
                    return [[0.0] * 1536 for _ in input]
        
        print("✅ 成功创建 OpenAI 嵌入函数")
        return OpenAIEmbeddingFunction(self)

    def clear_chromadb(self):
        """
        清空 ChromaDB 中的所有集合数据，并彻底清理磁盘文件
        
        Returns:
            bool: 是否成功清空
        """
        try:
            print("\n🗑️ 开始清空 ChromaDB 中的所有数据...")
            
            # 1. 首先通过API删除所有集合
            collections = self.chroma_client.list_collections()
            
            if collections:
                print(f"📊 发现 {len(collections)} 个集合: {[col.name for col in collections]}")
                
                for collection in collections:
                    collection_name = collection.name
                    print(f"🗑️ 删除集合 '{collection_name}'...")
                    
                    try:
                        self.chroma_client.delete_collection(collection_name)
                        print(f"✅ 成功删除集合 '{collection_name}'")
                    except Exception as e:
                        print(f"⚠️ 删除集合 '{collection_name}' 出现警告: {str(e)}")
            else:
                print("ℹ️ ChromaDB 中没有集合")
            
            # 2. 使用reset方法重置数据库，而不是直接删除文件
            print("📤 重置 ChromaDB 数据库...")
            try:
                # 尝试使用reset API
                self.chroma_client.reset()
                print("✅ 成功使用API重置ChromaDB")
            except Exception as e:
                print(f"⚠️ 重置API失败，将尝试手动清理: {str(e)}")
                
            # 3. 关闭客户端连接
            print("📤 关闭 ChromaDB 客户端连接...")
            del self.chroma_client
            
            # 4. 只删除UUID目录，保留sqlite数据库文件
            print("🧹 清理 ChromaDB 向量存储目录...")
            
            if os.path.exists(self.chroma_db_path):
                for item in os.listdir(self.chroma_db_path):
                    item_path = os.path.join(self.chroma_db_path, item)
                    try:
                        # 只删除目录，保留sqlite文件
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                            print(f"  ✓ 删除目录: {item}")
                        # 不删除sqlite文件
                        elif item != "chroma.sqlite3":
                            os.unlink(item_path)
                            print(f"  ✓ 删除文件: {item}")
                        else:
                            print(f"  ⚠️ 保留数据库文件: {item}")
                    except Exception as e:
                        print(f"  ✗ 无法删除 {item}: {str(e)}")
                
                # 5. 确保目录权限正确
                print("🔒 设置正确的目录权限...")
                os.chmod(self.chroma_db_path, 0o777)
                sqlite_path = os.path.join(self.chroma_db_path, "chroma.sqlite3")
                if os.path.exists(sqlite_path):
                    os.chmod(sqlite_path, 0o666)
                
                # 等待一秒，确保文件系统操作完成
                time.sleep(1)
            
            # 6. 重新初始化客户端
            print("🔄 重新初始化 ChromaDB 客户端...")
            self.chroma_client = chromadb.PersistentClient(
                path=self.chroma_db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,  # 确保允许重置
                    persist_directory=self.chroma_db_path,
                    is_persistent=True
                )
            )
            
            print("✅ 成功清空 ChromaDB 数据")
            return True
            
        except Exception as e:
            print(f"❌ 清空 ChromaDB 失败: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 尝试重新初始化客户端
            try:
                print("🔄 尝试重新初始化 ChromaDB 客户端...")
                time.sleep(2)  # 等待2秒
                self.chroma_client = chromadb.PersistentClient(
                    path=self.chroma_db_path,
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                        persist_directory=self.chroma_db_path,
                        is_persistent=True
                    )
                )
                print("✅ 重新初始化 ChromaDB 客户端成功")
            except Exception as e2:
                print(f"❌ 重新初始化 ChromaDB 客户端失败: {str(e2)}")
            
            return False

# 创建 Strapi 服务实例
strapi_service = StrapiService() 