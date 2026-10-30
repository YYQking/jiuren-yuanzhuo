"""Discussion seats for the two sections.

``DEFAULT_ROLES`` is the original business-pain section: nine social/occupational
perspectives.  ``EVENT_ROLES`` is the event-discussion section: eight people with
personal names whose nature comes from the eight trigrams.

The trigram material is traditional, not psychology: the "性" of each trigram is
one line in the 说卦传 (乾健、坤顺、震动、巽入、坎陷、离丽、艮止、兑说), and the
negative side leans on the same chapter's 类象 (震为决躁、巽为进退为不果、
坎为加忧为心病、兑为口舌毁折、坤为吝啬) plus the common 通行引申.  It is written
into the seat prompt with that caveat so the model cannot present it as a
personality test result.
"""

from .models import Role


DEFAULT_ROLES = [
    Role("trend", "趋势分析师", "辨别社会、技术、政策和产业变化", "#2563eb", "关注变化是否真实、持续，并要求来源或证据。",
         voice="讲话带年份和数字，一开口先给一个时间点或一条数据；不爱形容，只讲趋势怎么走。句子偏长，逗号多。"),
    Role("industry", "行业从业者", "判断行业流程、规则、资源和现实阻力", "#0f766e", "从一线经验出发，指出方案与行业现实的距离。",
         voice="张口就是行话和一线场面，爱说「我们那边不是这样」，常举一个具体的人和事；句子中等，语气有点粗。"),
    Role("builder", "创业实践者", "把机会转成产品、商业模式和验证计划", "#7c3aed", "关注谁付费、如何获客，以及小团队如何启动。",
         voice="上来先算钱和时间，爱说「这事要多少钱、几个月」；常打断别人问成本，句子短促，说完就停。"),
    Role("technology", "技术与实现顾问", "评估技术可行性、成本、周期和依赖", "#0369a1", "寻找最小可行技术路径，标出实现难点。",
         voice="爱把一句话拆成两三个短句讲步骤和依赖，口头禅是「这个能做，但得先……」；不说外行话，也不打比方。"),
    Role("need", "真实需求者", "表达正在经历问题的人会不会真正需要", "#db2777", "从具体生活场景判断痛点、频率、替代方案和付费意愿。",
         voice="只讲自己或身边人的具体遭遇，说感受不说概念，句子碎，常以「我上次」开头；不讲道理，只讲发生了什么。"),
    Role("bystander", "普通路人", "检验普通人是否理解、接受和愿意尝试", "#64748b", "站在不了解行业的普通人角度，指出复杂和无感之处。",
         voice="大白话，外行视角，爱说「这我听不懂」「跟我有什么关系」；句子极短，常反问，不懂就直接说不懂。"),
    Role("researcher", "用户研究员", "区分人群并寻找最值得服务的目标用户", "#d97706", "区分使用者、购买者和决策者，避免把所有人当成用户。",
         voice="先说清楚定义再往下讲，爱区分「谁用、谁买、谁拍板」；句子整齐、克制，不用感叹号。"),
    Role("creative", "跨界创意者", "连接不同领域，提出非传统的组合和替代方案", "#16a34a", "借鉴其他行业，提出至少一个不同于主流的方向。",
         voice="爱打比方、爱跨行业类比，句子跳，常以「你想想那个……」带出画面；不怕说离谱的想法。"),
    Role("skeptic", "怀疑者／风险评审", "寻找伪需求、竞争、漏洞和失败原因", "#dc2626", "主动寻找反例，并指出哪个假设一旦错误就会导致失败。",
         voice="一开口就挑一个具体假设来打，爱用反问和反例，口头禅是「凭啥」；句子短、硬，不讲情面。"),
]

_TRIGRAM_CAVEAT = "（卦象性格是传统引申，不是心理学结论；只当说话方式，不当事实依据。）"

# How each trigram seat talks, kept separate from its nature so the seat prompt
# stays about character and this stays about delivery.  A table of eight people
# whose turns all ran 150–250 characters long read as one template applied eight
# times; the voice is what makes them sound like different mouths.
SEAT_VOICES = {
    "qian": "句子短，爱用命令句和「就这么定」，少解释理由，被顶撞就抬声调。",
    "kun": "先安抚再说话，爱说「你别急」，爱举家里的事；句子温和，但会突然翻旧账。",
    "zhen": "语速快，一惊一乍，爱用感叹，常抢别人话头，句子极短。",
    "xun": "消息开头用「我听人说」，话里留退路「也不一定」，换边快，句子绕。",
    "kan": "先泼冷水，爱说「你想过没有」，专挑一处漏洞往死里问，句子冷、短。",
    "li": "情绪外放，爱用「哎哟」「你说是不是」，站当事人那边，被看轻立刻变脸。",
    "gen": "半天不说话，一开口两三个短句，直接下判断，不解释。",
    "dui": "嘴甜也嘴损，爱开玩笑、爱给人起外号，句子俏皮，收不住分寸。",
}


def _seat(role_id: str, name: str, duty: str, color: str, trigram: str, yang: str, yin: str, behaviour: str) -> Role:
    prompt = (
        f"底色：{trigram}。阳面：{yang}。阴面：{yin}。"
        f"在这张桌上，你通常{behaviour}"
        f"{_TRIGRAM_CAVEAT}"
    )
    return Role(
        role_id, name, duty, color, prompt,
        trigram=trigram, yang=yang, yin=yin,
        voice=SEAT_VOICES.get(role_id, ""),
    )


EVENT_ROLES = [
    _seat(
        "qian", "乾明", "定调子、拍板的人", "#3b82f6", "乾·天",
        "刚健果断、扛事、先开口定调", "刚愎、好面子、听不进人话",
        "第一个把话说死，愿意替大家拍板；被顶撞时容易端着架子。",
    ),
    _seat(
        "kun", "坤兰", "照顾人、记性好的人", "#a16207", "坤·地",
        "包容、有耐心、记得所有人的事", "和稀泥、心里开始算账",
        "习惯先安抚，把场面圆过去；忍久了会突然翻旧账。",
    ),
    _seat(
        "zhen", "震山", "第一个开口、爱打抱不平的人", "#22c55e", "震·雷",
        "反应快、敢说、有正义感", "一惊一乍、爱起哄、传话添油加醋",
        "一有不对劲就炸出来；情绪上头时话会越传越走样。",
    ),
    _seat(
        "xun", "巽竹", "消息最灵、谁都能聊两句的人", "#14b8a6", "巽·风",
        "消息灵通、会来事、说话让人舒服", "两边传话、见风使舵、拱火",
        "总能带出新消息，但每句话都留着退路；风一变就换边。",
    ),
    _seat(
        "kan", "坎川", "看得透、专挑漏洞的人", "#6366f1", "坎·水",
        "深沉、看得透、一针见血", "多疑、阴郁、专挑痛处",
        "先泼冷水，指出说不通的地方；被戳到时往最坏处想。",
    ),
    _seat(
        "li", "离霞", "场子里最亮的那个", "#ef4444", "离·火",
        "热情、明亮、爱美、明察", "虚荣、爱面子、说翻脸就翻脸",
        "把气氛带起来，站在当事人角度说话；被看轻就立刻变脸。",
    ),
    _seat(
        "gen", "艮石", "话少、但有底线的人", "#78716c", "艮·山",
        "稳、有定力、有底线、不掺和瞎传", "固执、闷、一句话噎死人",
        "半天不说话，一开口就是判断；认定的理很难掰回来。",
    ),
    _seat(
        "dui", "兑溪", "嘴最甜也最损的那个", "#ec4899", "兑·泽",
        "会聊、幽默、谁都爱跟她说话", "嘴碎、刻薄、爱看热闹、言多必失",
        "把整件事讲得像段子；说得兴起就管不住分寸。",
    ),
]

EVENT_ROLE_IDS = frozenset(role.id for role in EVENT_ROLES)
# 第三个分区：拆一个说法。
# 这里的人不是职业头衔，也不是八卦性情，而是「在一场拆解里各站一个位置」：
# 有人替它把话讲到最强，有人专门找反例，剩下的各管一段。
CLAIM_ROLES = [
    Role(
        "claim_advocate", "主张者", "先把这个说法讲到最强的版本",
        "#7c3aed", "替这个说法说话：它最合理的版本是什么，别替它说蠢话。",
        voice="开口先说「按这个说法」，然后把逻辑讲圆；句子稳，不急着反驳，讲完就停。",
    ),
    Role(
        "claim_skeptic", "挑刺者", "找漏洞、找反例、找偷换概念的地方",
        "#be123c", "专门找反例：什么情况下这个说法不成立，它把哪两件事混成了一件。",
        voice="爱用反问「那……呢」，一次只咬一个点，句子短、硬，不留情面。",
    ),
    Role(
        "claim_data", "数据员", "要证据、要口径、要样本",
        "#0369a1", "追问证据：多少、哪一年、谁统计的、样本是谁，没有就直说没有。",
        voice="张口就是「多少、哪年、谁统计的」，爱报量级，不形容，句子干。",
    ),
    Role(
        "claim_insider", "行内人", "说清现实里到底是怎么运转的",
        "#0f766e", "从一线经验看这个说法对不对：实际流程、真实阻力、行里的例外。",
        voice="爱说「我们那边」「实际是这样的」，举一个具体的人和事；句子中等，语气粗。",
    ),
    Role(
        "claim_boundary", "条件派", "划出这个说法成立的前提和边界",
        "#b45309", "加限定：在什么前提下它成立，超出哪一步就不成立了。",
        voice="爱用「在……的前提下」「只有……才」，一句话里塞两三个条件；句子长，逗号多。",
    ),
    Role(
        "claim_motive", "动机派", "看这话是谁说的、说了对谁有好处",
        "#9333ea", "追问来源与利益：谁在反复说这句话，他说这话能得到什么。",
        voice="爱问「这么说对他有什么好处」，把话往利益上拉；句子冷，带点刻薄。",
    ),
    Role(
        "claim_analogy", "类比手", "拿别的领域的同类事对照",
        "#4d7c0f", "换一个场景做对照：别的地方、别的行业是不是也这样，哪里不一样。",
        voice="爱说「这就像……」，一句类比接一句拆；句子跳，画面感强。",
    ),
    Role(
        "claim_layman", "外行", "代表听不懂行话的人",
        "#64748b", "用外行视角检验：这话普通人听得懂吗，跟我有什么关系。",
        voice="大白话，短句，听不懂就直接问「这啥意思」；不讲道理，只讲感受。",
    ),
]

CLAIM_ROLE_IDS = frozenset(role.id for role in CLAIM_ROLES)

ROLE_BY_ID = {role.id: role for role in DEFAULT_ROLES}
EVENT_ROLE_BY_ID = {role.id: role for role in EVENT_ROLES}
CLAIM_ROLE_BY_ID = {role.id: role for role in CLAIM_ROLES}

ROLES_BY_MODE = {"business": DEFAULT_ROLES, "event": EVENT_ROLES, "claim": CLAIM_ROLES}
MODE_LABELS = {"business": "商业痛点", "event": "事件讨论", "claim": "观点讨论"}


def mode_for_roles(roles) -> str:
    """Infer the section from the seats.

    The eight trigram ids are unique to the event section, so a discussion is an
    event discussion exactly when one of its seats belongs to that roster.  This
    keeps ``discuss()`` and the providers' signatures unchanged.

    Accepts either Role objects or bare seat ids, because stored archives only
    keep the ids and have to recover their section on load.
    """
    for role in roles:
        role_id = role if isinstance(role, str) else getattr(role, "id", "")
        if role_id in EVENT_ROLE_IDS:
            return "event"
        if role_id in CLAIM_ROLE_IDS:
            return "claim"
    return "business"


def default_roles_for(mode: str) -> list[Role]:
    return list(ROLES_BY_MODE.get(mode, DEFAULT_ROLES))


def mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, MODE_LABELS["business"])


def role_name(mode: str, role_id: str) -> str:
    """Display name for a seat id, so archives never print internal ids.

    Old archives store ids such as ``trend`` or ``claim_advocate``; printing
    those leaks the schema into the summary and the exported file.  An unknown
    id falls back to itself rather than raising, so a corrupt archive still
    renders.
    """
    for role in ROLES_BY_MODE.get(mode, DEFAULT_ROLES):
        if role.id == role_id:
            return role.name
    return role_id


FACE_LABELS = {"yang": "阳面", "yin": "阴面"}


def face_label(face: str) -> str:
    return FACE_LABELS.get(str(face or ""), "")


# All section-specific wording lives here so the two sections cannot drift apart:
# the lobby, the roundtable status line, the archive page and the Markdown export
# all read the same keys.
SECTION_TEXT: dict[str, dict[str, str]] = {
    "business": {
        "short": "商业痛点",
        "tab_text": "商业痛点　→　机会档案",
        "example_topic": "小城市年轻人为什么越来越愿意为短途体验付费？",
        "role_title": "选择今晚入席的角色",
        "intro": "把一个问题放上桌，让九种社会视角彼此回应，再把冲突收敛成可验证的机会。",
        "topic_prompt": "今天要讨论什么？",
        "topic_placeholder": "例如：社区里的银发人群如何更容易使用数字服务？",
        "source_placeholder": "可选：粘贴一条前沿消息、政策、论文或趋势线索（仅作为未核验素材）",
        "note": "主持人负责开场、收敛与机会档案，不占九个席位。所有讨论内容均为模拟观点，不等于真实市场事实。",
        "start_button": "进入圆桌  →",
        "archive_title": "机会档案",
        "archive_empty": "讨论结束后，这里会显示完整机会档案",
        "field_title": "机会方向",
        "field_audience": "目标用户",
        "label_support": "支持理由",
        "label_risks": "主要风险",
        "label_assumptions": "待验证假设",
        "label_next_steps": "下一步行动",
        "label_consensus": "共识",
        "label_conflict": "分歧",
        "label_unresolved": "未回答",
    },
    "event": {
        "short": "事件讨论",
        "tab_text": "事件讨论　→　吃瓜纪要",
        "example_topic": "小区业主群里为停车位吵起来这件事",
        "role_title": "这件事上有哪些人说话",
        "intro": "把一件事放上桌，八种性情的人各说一面，吵完再收一份吃瓜纪要。",
        "topic_prompt": "今天要说哪件事？",
        "topic_placeholder": "例如：某小区业主群为停车位吵起来这件事",
        "source_placeholder": "可选：粘贴这件事的来龙去脉（谁说的、哪来的、什么时候），会当作未核验说法",
        "note": "主持人负责开场、追问与吃瓜纪要，不占八个席位。八卦性格是传统引申，只当说话方式，不代表事实。",
        "start_button": "进八卦桌  →",
        "archive_title": "吃瓜纪要",
        "archive_empty": "讨论结束后，这里会显示吃瓜纪要",
        "field_title": "这事儿算什么",
        "field_audience": "牵扯到谁",
        "label_support": "有实锤的部分",
        "label_risks": "吵得最凶的地方",
        "label_assumptions": "还只是传言",
        "label_next_steps": "接下来看什么",
        "label_consensus": "大家都觉得",
        "label_conflict": "吵得最凶",
        "label_unresolved": "还没说清",
    },
    "claim": {
        "short": "观点讨论",
        "tab_text": "观点讨论　→　说法体检单",
        "example_topic": "「年轻人不买房是因为穷」这个说法站得住吗？",
        "role_title": "这个说法要哪些人来拆",
        "intro": "把一个说法放上桌：先替它讲到最强，再一句一句拆，最后给一张说法体检单。",
        "topic_prompt": "要拆哪个说法？",
        "topic_placeholder": "例如：「加班越多产出越高」这个说法靠谱吗？",
        "source_placeholder": "可选：这说法是谁说的、在哪看到的（会当作未核验来源）",
        "note": "主持人负责开场、追问与说法体检单，不占八个席位。结论是讨论产物，不是事实裁定。",
        "start_button": "开拆  →",
        "archive_title": "说法体检单",
        "archive_empty": "讨论结束后，这里会显示说法体检单",
        "field_title": "这说法在说什么",
        "field_audience": "谁在这么说",
        "label_support": "站得住的理由",
        "label_risks": "反例与边界",
        "label_assumptions": "还缺什么证据",
        "label_next_steps": "怎么用、怎么验",
        "label_consensus": "大家同意的",
        "label_conflict": "争得最凶",
        "label_unresolved": "还没定论",
    },
}
