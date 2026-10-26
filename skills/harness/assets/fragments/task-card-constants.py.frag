# Task cards are opt-in: everything below runs only when .harness/config.json has "task_cards".
CARD_STATES = ("草稿", "已批准", "实施中", "待验收", "已完成", "未通过", "阻塞")
ACCEPTANCE_STATES = ("待执行", "已执行", "待人工验收", "已通过", "未通过")
ACCEPTANCE_METHODS = ("script", "human")
CARD_STATES_TEXT = "/".join(CARD_STATES)
ACCEPTANCE_STATES_TEXT = "/".join(ACCEPTANCE_STATES)
ACCEPTANCE_REQUIRED_COLUMNS = ("ID", "方式", "证据位置", "状态", "记录人")
BLANK_VALUES = {"", "-", "—", "–", "无", "n/a", "na", "none", "tbd", "待填"}
