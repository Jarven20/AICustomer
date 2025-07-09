import os
import json
import jieba
from typing import List, Dict, Any

class HintService:
    def __init__(self):
        """初始化搜索提示服务"""
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.knowledge_base_file = os.path.join(self.data_dir, "strapi_knowledge_parsed.json")
        self.hint_file_path = os.path.join(self.data_dir, "search_hints.json")
        self.hint_list = []
        self.hint_map = {}
        self.is_initialized = False

        # 添加金融领域常见词汇到分词词典
        jieba.add_word("k线")
        jieba.add_word("k线图")
        jieba.add_word("均线")
        jieba.add_word("MACD")
        jieba.add_word("KDJ")

        print("搜索提示服务初始化中...")
        # 初始化时尝试加载一次
        self.initialize()

    def initialize(self):
        """从 search_hints.json 初始化搜索提示列表 (如果文件存在)"""
        if self.is_initialized:
            # print("搜索提示服务已经初始化，跳过") # 不重复打印
            return

        try:
            # 检查提示文件是否存在
            if not os.path.exists(self.hint_file_path):
                print(f"提示文件不存在: {self.hint_file_path}，将等待生成...")
                self.is_initialized = True # 即使文件不存在，也标记为初始化，避免重复尝试
                return # 不尝试加载

            print(f"加载提示文件: {self.hint_file_path}")
            if os.path.getsize(self.hint_file_path) == 0:
                 print(f"警告: 提示文件为空: {self.hint_file_path}")
                 self.hint_list = []
                 self.hint_map = {}
                 self.is_initialized = True
                 return

            with open(self.hint_file_path, 'r', encoding='utf-8') as f:
                try:
                    hint_data = json.load(f)
                except json.JSONDecodeError as json_err:
                    print(f"错误: 解析提示文件 JSON 失败: {json_err}")
                    self.is_initialized = False # 解析失败，标记未初始化
                    return

            self.hint_list = hint_data.get("hints", [])
            self.hint_map = hint_data.get("hint_map", {})

            print(f"成功加载 {len(self.hint_list)} 条搜索提示")

            if self.hint_list:
                print("提示列表示例:")
                for i, hint in enumerate(self.hint_list[:5]):
                    print(f"  {i+1}. {hint}")

            self.is_initialized = True

        except Exception as e:
            print(f"初始化搜索提示时发生未知错误: {str(e)}")
            import traceback
            traceback.print_exc()
            self.is_initialized = False

    def generate_and_load_hints(self) -> bool:
        """从知识库解析文件生成搜索提示文件，并加载到内存"""
        print(f"🔄 开始生成搜索提示文件...")
        print(f"源文件: {self.knowledge_base_file}")
        if not os.path.exists(self.knowledge_base_file):
            print(f"❌ 错误: 知识库文件不存在: {self.knowledge_base_file}")
            # 尝试从全量文件生成解析文件（如果需要）
            full_file_path = os.path.join(self.data_dir, "api_im-customer-service-knowledge-bases_full.json")
            if os.path.exists(full_file_path):
                print(f"尝试从全量文件 {full_file_path} 生成解析文件...")
                try:
                    # 这里需要获取StrapiService实例来调用解析方法
                    # 最好是在调用此方法前确保解析文件已生成
                    from app.services.strapi_service import strapi_service
                    if strapi_service.parse_knowledge_json():
                        print("✅ 成功生成知识库解析文件。")
                        # 再次检查
                        if not os.path.exists(self.knowledge_base_file):
                            print(f"❌ 错误: 尝试生成后，知识库解析文件仍不存在。")
                            return False
                    else:
                        print(f"❌ 错误: 生成知识库解析文件失败。")
                        return False
                except Exception as parse_e:
                    print(f"❌ 从全量文件生成解析文件失败: {parse_e}")
                    return False
            else:
                print(f"❌ 错误: 全量知识库文件也不存在: {full_file_path}")
                return False

        try:
            with open(self.knowledge_base_file, 'r', encoding='utf-8') as f:
                knowledge_data = json.load(f)

            hints = []
            hint_map = {}
            print(f"从 {self.knowledge_base_file} 加载了 {len(knowledge_data)} 条记录用于生成提示")
            for item in knowledge_data:
                faq = item.get('FAQ')
                item_id = str(item.get('id', ''))
                if faq and item_id:
                    individual_faqs = faq.split('\n')
                    for individual_faq in individual_faqs:
                        clean_faq = individual_faq.strip()
                        if clean_faq:
                            if clean_faq not in hint_map:
                                hints.append(clean_faq)
                                hint_map[clean_faq] = item_id

            hint_data_to_save = {
                "hints": hints,
                "hint_map": hint_map
            }

            os.makedirs(self.data_dir, exist_ok=True)
            os.chmod(self.data_dir, 0o777)

            with open(self.hint_file_path, 'w', encoding='utf-8') as f:
                json.dump(hint_data_to_save, f, ensure_ascii=False, indent=2)
            os.chmod(self.hint_file_path, 0o666)

            print(f"✅ 成功生成提示文件: {self.hint_file_path}，包含 {len(hints)} 条提示")

            # 生成后直接加载
            self.hint_list = hints
            self.hint_map = hint_map
            self.is_initialized = True
            print(f"✅ 新生成的提示已加载到内存")
            return True

        except FileNotFoundError:
             print(f"❌ 错误: 读取知识库文件时发生 FileNotFoundError: {self.knowledge_base_file}")
             return False
        except json.JSONDecodeError as json_e:
             print(f"❌ 错误: 解析知识库 JSON 文件失败: {json_e}")
             return False
        except Exception as e:
            print(f"❌ 生成提示文件时发生未知错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def search_hints(self, query: str, limit: int = 10) -> List[str]:
        """
        根据用户输入查找可能的问题补全
        """
        # 不再自动调用 initialize
        if not self.is_initialized or len(self.hint_list) == 0:
             print("提示服务未初始化或列表为空，无法搜索。") # 增加日志
             return []

        if not query or len(query) < 1:
            return []

        query_words = set(jieba.cut(query))
        scored_hints = []
        for hint in self.hint_list:
            score = 0.0
            if hint.lower().startswith(query.lower()):
                score = 1.0
            elif query.lower() in hint.lower():
                score = 0.8
            else:
                hint_words = set(jieba.cut(hint))
                common_words = query_words & hint_words
                if common_words:
                    score = len(common_words) / len(query_words) * 0.6

            if score > 0:
                scored_hints.append((score, hint))

        scored_hints.sort(key=lambda x: x[0], reverse=True) # 按分数排序
        # print(f"搜索 '{query}' 的原始得分提示: {scored_hints[:limit+5]}") # 调试日志
        result = [hint for _, hint in scored_hints[:limit]]
        # print(f"最终返回提示: {result}") # 调试日志
        return result

    def get_hint_source(self, hint: str) -> str:
        """获取提示对应的知识库项ID"""
        return self.hint_map.get(hint, "")

    def refresh(self):
        """刷新搜索提示列表，尝试重新加载文件"""
        print("🔄 刷新搜索提示列表...")
        self.hint_list = []
        self.hint_map = {}
        self.is_initialized = False
        # 调用 initialize 尝试加载现有文件
        self.initialize()
        # 不再自动生成，如果需要更新，应该调用 generate_and_load_hints
        if self.is_initialized:
             print(f"✅ 搜索提示刷新/加载完成，当前共有 {len(self.hint_list)} 条提示")
             return len(self.hint_list) > 0
        else:
             print(f"❌ 搜索提示刷新失败或文件不存在")
             return False


# 创建服务实例
hint_service = HintService()
