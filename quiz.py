class Quiz:

    def __init__(self, type_, question, options, correct_option_id=None, lang='eng'):
        self.type_: str = type_
        self.lang: str = lang
        self.question: str = question
        self.options: list[str] | str = options
        self.correct_option_id: int = correct_option_id
