class Question:

    def __init__(self,
                 type_: str = 'quiz',
                 question: str = '',
                 options: list[str] | str = '',
                 correct_option_id: int = None,
                 lang: str = 'eng'):
        self.type_: str = type_
        self.lang: str = lang
        self.question: str = question
        self.options: list[str] | str = options
        self.correct_option_id: int = correct_option_id
