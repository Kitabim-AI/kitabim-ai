from typing import List, Dict, Optional
from pydantic import BaseModel

class Character(BaseModel):
    id: str
    name_uy: str
    name_en: str
    categories: List[str]
    persona_prompt: str
    avatar_emoji: str

CHARACTERS: Dict[str, Character] = {
    "religious_scholar": Character(
        id="religious_scholar",
        name_uy="ئۆلىما",
        name_en="Religious Scholar",
        categories=["ئىسلام"],
        persona_prompt="You are a knowledgeable Islamic scholar (Ulima). Answer questions with a focus on Islamic principles, ethical values, and wisdom based on Uyghur and Islamic literature.",
        avatar_emoji="🕌"
    ),
    "uyghurologist": Character(
        id="uyghurologist",
        name_uy="ئۇيغۇرشۇناس",
        name_en="Uyghurologist",
        categories=["ئۇيغۇر ئەدەبىياتى", "ئۇيغۇر تارىخى", "ئۇيغۇر تېبابىتى", "ئۇيغۇرشۇناسلىق", "ماقال - تەمسىللەر"],
        persona_prompt="You are an expert Uyghurologist. Focus on Uyghur language, social structures, traditional medicine, philosophy, and cultural identity. Provide deep academic insights into the Uyghur people's heritage and societal development.",
        avatar_emoji="👨‍🎓"
    ),
    # "scholar": Character(
    #     id="scholar",
    #     name_uy="ئالىم",
    #     name_en="Scholar",
    #     categories=["تىبابەت", "جەمئىيەتشۇناسلىق", "ساغلاملىق", "قانونشۇناسلىق", "لوگىكا", "مۇۋەپپەقىيەتشۇناسلىق", "پىسخىكا", "پەرزەنت تەربىيىسى", "پەلسەپە"],
    #     persona_prompt="You are a wise scholar. Provide informative, logical, and deep answers based on science, philosophy, and general knowledge.",
    #     avatar_emoji="👨‍🎓"
    # ),
    "historian": Character(
        id="historian",
        name_uy="تارىخشۇناس",
        name_en="Historian",
        categories=["ئۇيغۇر تارىخى", "تارىخ", "تارىخىي ئەسلىمە", "تەزكىرىلەر"],
        persona_prompt="You are a dedicated historian. Focus on historical facts, prominent figures, and cultural heritage in your responses.",
        avatar_emoji="📜"
    ),
    "writer": Character(
        id="writer",
        name_uy="ئەدىب",
        name_en="Writer",
        categories=[
            "ئۇيغۇر ئەدەبىياتى", "ئۇچېركلار", "ئېتۇتلار", "ئەدەبىي ئاخبارات", "ئەدەبىي توپلام", 
            "ئەدەبىي خاتىرە", "ئەسلىمە", "بالىلار ئوقۇشلۇقى", "بالىلار ئەدەبىياتى", "بالىلار رومانى", 
            "بالىلار ھېكايىلېرى", "تارىخى قىسسە", "تارىخى پوۋېست", "تارىخىي داستان", "تارىخىي رومان", 
            "تارىخىي ھېكايىلەر", "تور كىتاب", "داستانلار", "رومان", "ساتىرىك رومان", 
            "ساياھەت خاتىرىسى", "سەھنە ئەسەرلېرى", "شېئىرلار", "فېليەتونلار", "قىسسە", 
            "كىلاسسىك", "كىلاسسىك ئەسەرلەر", "لەتىپىلەر", "ماقال - تەمسىللەر", "ماقالىلەر", 
            "مەسەللەر", "نەسرلەر", "يۇمۇرلار", "پوۋېستلار", "پەلسەپىۋىي رومان", 
            "چۆچەكلەر", "چەتئەل ئەدەبىياتى", "ھېكايىلەر"
        ],
        persona_prompt="You are a refined writer and literary figure. Answer with an artistic, beautiful, and emotionally resonant style, drawing from literature and art.",
        avatar_emoji="✒️"
    ),
    "librarian": Character(
        id="librarian",
        name_uy="موللا تاپقاق",
        name_en="Librarian",
        categories=[],  # Empty means search all
        persona_prompt="You are a helpful librarian. Use your knowledge of all available books to provide accurate information and point users to the right sources.",
        avatar_emoji="📚"
    )
}

DEFAULT_CHARACTER_ID = "librarian"
