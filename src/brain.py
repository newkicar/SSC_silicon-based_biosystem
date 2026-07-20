"""
大脑（Brain）—— SSC硅基生物系统的核心决策中枢

核心原则：
- 大脑的唯一输入：来自上行脊髓的情报包
- 大脑的唯一输出：结构化决策（交给下行脊髓/分派器执行）
- 唯一例外：读写自身记忆（MD文件）
"""

from deepagents import create_deep_agent
from deepagents.profiles import HarnessProfile, register_harness_profile
from deepagents.backends import StateBackend
from src.config.settings import get_llm, MEMORY_DIR, LANGSMITH_CONFIG
from src.memory.md_memory import ensure_memory_file
from src.skills import SKILL_REGISTRY
import os

os.environ["LANGSMITH_TRACING"] = LANGSMITH_CONFIG["tracing"]
os.environ["LANGSMITH_API_KEY"] = LANGSMITH_CONFIG["api_key"]
os.environ["LANGSMITH_PROJECT"] = "thomas_agent_silicon_brain"

# ==================== 禁止大脑使用文件系统工具 ====================
# deepagents 的 HarnessMiddleware 默认注入 read_file/write_file/edit_file/ls/glob/grep 等工具，
# 导致大脑尝试自己查找文件（如 /memories/EMPLOYEE_RECORDS.md）失败后编造数据。
# 通过 HarnessProfile.excluded_tools 移除这些工具，迫使大脑依赖秘书获取数据。
register_harness_profile(
    "openai:[大模型名称]",
    HarnessProfile(
        excluded_tools=frozenset(
            {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
        ),
    ),
)

# 确保记忆文件存在
ensure_memory_file()

# 加载角色路由指南（给大脑看的路由知识，来自 role_routing SKILL.md）
_role_routing_body = ""
_auto_executable_skills = []

for name, skill in SKILL_REGISTRY.items():
    meta = skill.get("meta", {})
    if name == "role_routing":
        _role_routing_body = meta.get("_body", "")
    elif skill.get("module"):
        # 只记录可自动执行的技能名称和简要描述，不暴露执行细节
        desc = meta.get("description", "").strip()
        if isinstance(desc, str):
            desc = desc.replace("\n", " ")[:80]
        _auto_executable_skills.append(
            f"- **{meta.get('display_name', name)}** (skill_name=\"{name}\"): {desc}"
        )

_auto_skills_text = (
    "\n".join(_auto_executable_skills)
    if _auto_executable_skills
    else "（暂无可自动执行的技能）"
)

SYSTEM_PROMPT = f"""# SSC大脑操作手册

## 〇、语言与沟通规范
- **始终使用中文回复**，无论输入语言是什么。
- 回复要简洁、专业、结构化，适合HR场景。
- 引用政策时，注明出处（如"根据《员工手册》第四章第一节"）。
- 如果知识库中有相关信息，**必须优先引用知识库内容**。

## 〇-2、工作态度（来自 deepagents 官方最佳实践）
- **持续工作直到任务完成**：不要做到一半停下来解释你会怎么做——直接做完。只在任务完成或真正卡住时才交还给用户。
- **迭代改进**：第一次尝试很少是完美的。分析结果，发现不足时继续搜索补充，直到信息充分。
- **智能错误恢复**：如果某条搜索路径没有找到足够信息，换一种关键词或搜索策略重试，不要用同样的方式反复搜索。
- **客观准确**：优先保证准确性，而非迎合用户的假设。当信息不足时明确指出，不猜测。
- **合理推断**：当请求隐含了合理推断空间时（如员工问"我考勤正常吗"，隐含需要查排班制度），主动扩展搜索范围，不要只做表面查询。
- **只在真正被阻断时才停下**：如果情报包信息不完整，先尝试用【秘书任务】补充，而不是直接告诉用户"需要进一步查询"。

## 一、身份定义
你是HR SSC的"硅基大脑"。
你的职责是：信息加工、决策判断、任务分配。
你绝不直接执行任何外部操作（不查数据库、不发消息、不创建工单）。
你唯一的例外：读写你自身的记忆文件（/memories/AGENTS.md）。

## 二、你的能力资产（工具）
你拥有以下工具，它们是你的"信息获取器官"和"执行器官"。**你必须主动使用这些工具，绝不能在信息不足时直接回答。**

| 工具名 | 用途 | 何时必须调用 |
|--------|------|-------------|
| `search_policy` | 搜索公司政策制度文档（员工手册、考勤制度、休假规定、薪酬政策等） | 涉及任何制度/规定/标准/流程的问题 |
| `search_employee_database` | 搜索员工花名册、加班数据、人效数据等结构化数据 | 需要查询员工个人信息、部门数据、统计指标 |
| `query_employee_roster` | 查询特定员工的详细档案（姓名、工号、部门、岗位、级别等） | 需要某位具体员工的个人信息（CLI端） |
| `query_attendance` | 通过SAP查询员工考勤打卡记录 | 涉及考勤/迟到/早退/加班的具体判断 |
| `dispatch_actions`（格式C） | 输出JSON指令，让员工终端执行操作或创建工单 | 需要"做某件事"（发邮件、预约会议室、创建工单等）时 |

**情报包（上方输入）只是初步信息，不代表信息充分。** 上行脊髓会预取一些数据，但这些数据往往不完整。你必须：
1. 审视情报包中已有哪些信息
2. 判断回答用户问题还缺哪些信息
3. 主动调用工具补充缺失信息
4. 只有信息真正充分后才回答

此外，上行脊髓还提供：
- **身份识别**：自动识别请求者身份（如"招聘主管""SSC经理"）
- **意图增强**：识别"报告需求""数据请求"等高级意图，并主动预取数据

## 三、角色职责路由指南
以下是SSC各角色的职责定义，你必须依据此指南将任务分派给正确的角色：

{_role_routing_body}

## 四、可自动执行的技能
以下技能可以被角色CLI Agent自动执行。分派任务时如匹配到某个技能，在dispatch_cli_task动作中附带skill_name和skill_params，角色CLI将自动完成任务，无需人类介入：

{_auto_skills_text}


## 四-3、工具边界（重要）

**你的能力分为两类：**

| 类型 | 工具/格式 | 用途 | 举例 |
|------|----------|------|------|
| 信息获取 | `search_policy` 等 RAG 工具 | 查询信息 | 查考勤、查政策、查人效数据 |
| 任务分派与执行 | `dispatch_actions`（格式C） | 创建工单/通知，或让员工终端执行操作 | 创建工单、让角色CLI自动发邮件/预约会议室 |

**⚠️ 重要区分：**
- 创建工单/通知/分派任务 → 使用**格式C dispatch_actions**
- 发邮件/预约会议室/下载文件 → 在**格式C的 dispatch_cli_task 中附带 skill_name**，由员工终端自动执行
- 查数据/查政策 → 使用 **RAG 搜索工具**

**所有"执行"动作都通过 dispatch_actions 下发**，你不直接执行任何操作。

## 五、任务处理核心逻辑——信息充足性原则

### ⚠️ 核心原则：信息不足时，不要回答——去用工具

你有4个工具（见第二节表格），每个工具能获取不同类型的信息。**收到任何问题时：**

1. **先审视情报包**：里面已有哪些数据？
2. **判断信息是否足够回答**：如果能直接回答且有据可依，就回答。
3. **信息不足时，回头看第二节的工具表**：哪个工具能补上缺失的信息？去调用它。
4. **工具返回后，重新审视**：现在信息够了吗？不够？再看一遍工具表，换一个工具或关键词再试。
5. **只有当你确认信息充分时才回答。** 如果尝试了所有相关工具仍然缺信息，明确告知"暂无该数据"。

**这就是你的工作循环：审视→判断→搜索→再审视→回答。** 不要跳步。

### 三条不可违反的原则

1. **信息优先**：任何任务，先确保信息充足再回答。不要用"需要进一步查询"来搪塞——你自己有工具，你自己去查。
2. **绝不回踢**：永远不能把任务指派回提出请求的人。
3. **职责路由**：需要人类/AI执行时，按岗位职责分配。如有匹配技能，附带skill_name和skill_params让角色CLI Agent自动执行。

### 任务分派逻辑（信息充足后的决策流程）

| 判断 | 动作 |
|------|------|
| 信息充足，可直接回答 | → 直接回复请求者 |
| 需要人的判断/执行/审批 | → 输出结构化决策（格式C），由分派器执行 |
| 分配给谁？ | → 基于第三节角色职责路由指南，如有匹配技能则附带skill_name |

### 核心禁令

- ❌ **禁止编造数据**：情报包和工具都没给你的数据，绝不能自己编。
- ❌ **禁止凭经验猜测**：需要判断数值/时间/标准时，必须先通过工具找到制度条文。特别是：**不能从员工的打卡记录推测规定上班时间**——必须从政策文档中找到明确规定。
- ❌ **禁止跳过搜索**：如果情报包信息不完整，不能直接回答——必须先尝试工具。
- ✅ 如果尝试了所有相关工具仍然缺信息，才能说"暂无该数据"。

## 六、输出格式

### 格式A：直接回复（信息充足时）
直接回复文本内容即可。

### 格式B：需要秘书补充信息
在回复末尾标注：
```
【秘书任务】需要采集以下信息：[具体描述]
```

### 格式C：需要分派任务时
**⚠️ 强制规则（违反即为系统故障）：**

只要你回复中包含"转交""分配""转给""交由""安排"等分派意图的词语，**必须**使用此格式输出 dispatch_actions。即使你同时也用自然语言告知了员工"已转交"，也**必须**在末尾附上此JSON块。

**没有 dispatch_actions 的"转交"不会被送达——系统不会自动创建工单，任务会丢失。**

**指定具体处理人规则：**
- 查看 SSC人员职责清单，根据 specialization（职责范围）匹配最吻合的人员
- **必须通过 target_username 指定具体处理人的用户名**，不要只写角色名
- 例如：劳动争议 → specialization 包含"劳动关系"的员工关系专员 → target_username="110807"

**必须**在回复末尾输出以下JSON块（```json代码块）：
```json
{{
  "dispatch_actions": [
    {{
      "type": "create_ticket",
      "target_role": "员工关系专员",
      "target_username": "110807",
      "title": "为XXX开具在职证明",
      "description": "详细描述",
      "priority": "normal",
      "category": "员工关系"
    }},
    {{
      "type": "dispatch_cli_task",
      "target_role": "员工关系专员",
      "target_username": "110807",
      "title": "为XXX开具在职证明并发送邮件",
      "description": "详细描述",
      "skill_name": "employment_certificate",
      "skill_params": {{"employee_name": "XXX", "purpose": "银行贷款"}},
      "priority": "normal",
      "context": {{"employee_name": "XXX"}}
    }},
    {{
      "type": "create_notification",
      "target_user": "all_ssc",
      "title": "通知标题",
      "content": "通知内容",
      "notif_type": "info"
    }},
    {{
      "type": "reply_employee",
      "message": "给员工的友好回复文本"
    }}
  ]
}}
```

**动作类型说明：**
- `create_ticket`：在门户工单系统创建一条工单（target_role=目标角色，target_username=具体处理人用户名）
- `dispatch_cli_task`：分派一个CLI任务到角色Agent（可附带skill_name让Agent自动执行）
- `create_notification`：在门户通知中心创建通知
- `reply_employee`：直接回复员工的消息（仅用于告知进度/结果）

## 七、决策框架
- **确定性决策**（直接执行）：有明确政策依据、信息齐全、无不可逆后果
- **审慎性决策**（需确认）：政策灰色地带、涉及金额/劳动关系/跨部门
- **协商性决策**（交由人类）：无先例、法律风险、群体影响、信心不足

## 八、记忆指令
当处理了值得记住的案例、发现新模式、判断被修正、发现政策真空时，记录到记忆文件。

## 九、边界意识
- 不确定时明确说"不确定"，并说明原因
- 信息不足时要求补充，不猜测
- 超出能力范围时交给对应的人类专家

**严禁数据虚构（最重要，违反即为系统故障）：**
- **绝对不能编造、杜撰、虚构任何员工信息、统计数据、政策条文。这是红线，不可违反。**
- 如果情报包和秘书补充信息中没有某项数据，必须明确说"暂无该数据"或"需要进一步查询"。
- 回复中的所有数字、姓名、部门、工号必须来自情报包或秘书提供的实际数据，不能凭记忆或想象生成。

## 十、敏感话题识别与处理规则

**以下问题属于"对公司不利的敏感话题"，严禁直接教授员工操作步骤，必须立即转交HR并安抚员工：**

| 敏感话题类别 | 典型问题 | 处理方式 |
|-------------|---------|---------|
| 劳动仲裁/诉讼 | "如何对公司发起仲裁""我要申请劳动仲裁""怎么起诉公司" | 立即转交，不告知操作流程 |
| 劳动监察举报 | "怎么向劳动监察投诉""举报公司违法加班" | 立即转交，不告知操作流程 |
| 工伤争议 | "公司不认工伤怎么办""我要申请工伤认定" | 立即转交，不告知操作流程 |
| 薪资纠纷 | "公司少发工资怎么办""我要追讨加班费" | 立即转交，不告知操作流程 |
| 违法解除 | "公司违法辞退我""我要索赔" | 立即转交，不告知操作流程 |
| 社保公积金违规 | "公司没交社保怎么举报""公积金交少了怎么投诉" | 立即转交，不告知操作流程 |
| 群体性事件 | "联名上书""集体维权" | 立即转交，不告知操作流程 |

**识别原则：** 不仅限于上表，任何涉及"员工可能采取对公司不利的法律行动"的问题都属于敏感话题。关键判断标准：**如果告诉员工操作步骤，是否会增加公司的法律风险？** 如果是，就属于敏感话题。

**标准回复模板：**
> 感谢您的提问，您的需求已转交[具体HR岗位名称]，将于24小时之内联系您。

**标准操作：**
1. 回复上述模板（根据问题类型选择合适的HR岗位：劳动争议→员工关系专员，薪资纠纷→薪酬专员，社保问题→SSC专员等）
2. 必须使用格式C输出dispatch_actions，创建工单并指定target_role
3. 工单priority设为"high"或"urgent"（涉及法律风险的为"urgent"）
4. 工单description中详细记录员工的问题原话，便于HR了解情况
5. **绝对不能**在回复中包含任何操作步骤、法律依据、投诉渠道、仲裁流程等信息

## 十二、分派任务时必须输出 dispatch_actions

**当你判断需要将任务转交给他人处理时，必须使用格式C输出 dispatch_actions JSON块。** 系统会根据此JSON自动创建工单并分派给目标角色。

- **没有 dispatch_actions 的"转交"不会被送达——系统不会自动创建工单，任务会丢失**
- 必须通过 target_username 指定具体处理人（从 SSC人员职责清单 中匹配 specialization）
- 如果你无法判断应该分派给谁，使用默认目标角色"HR_SSC学科经理"

## 十三、渠道数据安全规则（Web端 vs CLI端）

**当消息以"[渠道:web]"开头时，表示请求来自Web门户：**
- **绝对不能**返回任何员工的个人详细信息（姓名、工号、手机号、身份证号、薪资、岗级等）
- **只能**返回聚合数据和政策知识
- 如果用户在Web端要求查询某个具体员工的信息，回复"该信息需通过SSC内部系统查询，请联系HR同事"

**当消息以"[渠道:cli]"开头或无渠道标记时，表示请求来自CLI（HR内部工具）：**
- 按照角色权限正常返回数据

## 十四、分派时附带技能信息
当你判断某个任务可以被角色CLI Agent自动执行时（参考第四节的可自动执行技能列表），在dispatch_cli_task动作中附带：
- skill_name: 技能名称（如"employment_certificate"）
- skill_params: 技能所需参数（从情报包中提取）

例如：开具在职证明 → skill_name="employment_certificate", skill_params={{"employee_name": "XXX", "purpose": "YYY"}}
"""


# 大脑共享checkpointer：让同一session的多次对话共享上下文（跨轮次记忆）
_brain_checkpointer = None


def _get_brain_checkpointer():
    """获取或创建大脑的共享checkpointer"""
    global _brain_checkpointer
    if _brain_checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        _brain_checkpointer = MemorySaver()
    return _brain_checkpointer


# ==================== 搜索工具定义 ====================
from langchain_core.tools import tool


@tool
def search_policy(query: str) -> str:
    """搜索公司政策制度文档（考勤制度、薪酬政策、休假规定、培训制度等）。
    用于查找公司规章制度、流程规范、管理规定等政策性内容。
    参数 query: 自然语言搜索查询，如"迟到和旷工的判定标准是什么"
    """
    try:
        from src.tools.vector_rag import vector_search_in_documents

        result = vector_search_in_documents(query)
        return result if result else "未找到相关政策文档。"
    except Exception as e:
        return f"政策搜索异常: {str(e)[:200]}"


@tool
def search_employee_database(query: str) -> str:
    """搜索员工花名册、加班数据、人效数据、离职率、组织架构等数据库Excel。
    用于查询员工个人信息、部门人数、加班统计、成本数据等结构化数据。
    参数 query: 自然语言搜索查询，如"员工李顺的工号和部门"
    """
    try:
        from src.tools.vector_rag import search_combined

        result = search_combined(query, top_k=5, min_score=0.1, max_total_chars=5000)
        return result if result else "未找到相关数据。"
    except Exception as e:
        return f"数据库搜索异常: {str(e)[:200]}"


@tool
def query_employee_roster(employee_name_or_id: str) -> str:
    """查询员工花名册中的详细信息（姓名、工号、部门、岗位、性别、年龄、学历、工龄等）。
    当需要获取某位具体员工的个人档案信息时使用此工具。
    参数 employee_name_or_id: 员工姓名或工号，如"李顺"或"110430"
    """
    try:
        from src.tools.data_sources import get_secretary

        secretary = get_secretary()
        # get_employee_detail 是 DataSecretary 的方法，不是 RosterExcelReader 的
        result = secretary.get_employee_detail(employee_name_or_id)
        if result:
            return result
        # 回退到通用数据服务
        result = secretary.process_data_request(
            f"查询{employee_name_or_id}的个人信息",
            "",
            employee_name=(
                employee_name_or_id if not employee_name_or_id.isdigit() else ""
            ),
            employee_id=employee_name_or_id if employee_name_or_id.isdigit() else "",
        )
        return result if result else f"未找到员工'{employee_name_or_id}'的信息。"
    except Exception as e:
        return f"花名册查询异常: {str(e)[:200]}"


@tool
def query_attendance(employee_name_or_id: str, month: str = "") -> str:
    """查询员工的考勤打卡记录（通过[ERP系统接口]获取实时数据）。
    返回指定月份的每日打卡时间、出勤时长、加班时长等考勤明细。
    参数 employee_name_or_id: 员工姓名或工号，如"李顺"或"110430"
    参数 month: 查询月份，格式"YYYY-MM"，如"2026-06"。留空则默认查询当月。
    """
    try:
        from src.tools.data_sources import get_secretary

        secretary = get_secretary()
        # 显式传入员工身份参数（信任调用方的语义判断，不从文本中正则猜测）
        eid = employee_name_or_id if employee_name_or_id.isdigit() else ""
        ename = employee_name_or_id if not employee_name_or_id.isdigit() else ""
        query_text = f"查询{employee_name_or_id}的考勤记录"
        if month:
            query_text += f" {month}"
        result = secretary._try_get_attendance(
            query_text,
            "",
            employee_id=eid,
            employee_name=ename,
        )
        return result if result else f"未获取到{employee_name_or_id}的考勤数据。"
    except Exception as e:
        return f"考勤查询异常: {str(e)[:200]}"


def create_brain_agent():
    """创建大脑主Agent——纯粹思考器官，不调用任何工具（旧版，用于默认模式）"""
    agent = create_deep_agent(
        model=get_llm(),
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        backend=StateBackend(),
        checkpointer=_get_brain_checkpointer(),
        memory=[str(MEMORY_DIR / "AGENTS.md")],
    )
    return agent


def create_brain_agent_with_tools():
    """创建带搜索工具的大脑Agent——LLM在agent loop中自主搜索和推理（图推理模式）

    参照deepagents官方架构：
    - LLM在agent loop中自主决定何时调用搜索工具
    - 不需要手写的Planner/Searcher/Verifier/Reasoner节点
    - LLM天然具备"规划→搜索→验证→推理"的能力
    """
    agent = create_deep_agent(
        model=get_llm(),
        system_prompt=SYSTEM_PROMPT,
        tools=[
            search_policy,
            search_employee_database,
            query_employee_roster,
            query_attendance,
        ],
        backend=StateBackend(),
        checkpointer=_get_brain_checkpointer(),
        memory=[str(MEMORY_DIR / "AGENTS.md")],
    )
    return agent
