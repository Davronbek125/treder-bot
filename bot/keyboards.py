from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Telefon ekranining pastida turadigan qulay va tezkor asosiy menyu tugmalari.
    """
    kb = [
        [
            KeyboardButton(text="🎯 Aniq Savdo Signali"),
            KeyboardButton(text="📊 XAUUSD Bozor Tahlili")
        ],
        [
            KeyboardButton(text="🧠 SMC & Order Block"),
            KeyboardButton(text="📰 Dunyo Yangiliklari")
        ],
        [
            KeyboardButton(text="⚡ M1 Skalping"),
            KeyboardButton(text="🛡 Lot Kalkulyatori")
        ],
        [
            KeyboardButton(text="📊 Statistika"),
            KeyboardButton(text="⚙️ Sozlamalar & Yordam")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_signal_inline_kb(current_tf: str = "15m", signal_id: int = 0) -> InlineKeyboardMarkup:
    """
    Signal xabari ostidagi interaktiv vaqt oralig'i (Timeframe) va yangilash tugmalari.
    """
    tfs = [("M5", "5m"), ("M15", "15m"), ("H1", "1h"), ("H4", "4h"), ("D1", "1d")]
    row1 = []
    for label, tf in tfs:
        text = f"✅ {label}" if tf == current_tf else label
        row1.append(InlineKeyboardButton(text=text, callback_data=f"sig_tf:{tf}"))

    row2 = [
        InlineKeyboardButton(text="🔄 Yangilash", callback_data=f"sig_refresh:{current_tf}"),
        InlineKeyboardButton(text="🛡 Lotni hisoblash", callback_data="open_calc")
    ]
    
    kb = [row1, row2]
    if signal_id > 0:
        kb.append([InlineKeyboardButton(text="✅ Bitim ochildi (Kuzatish)", callback_data=f"trade_opened:{signal_id}")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_analysis_inline_kb(current_tf: str = "15m") -> InlineKeyboardMarkup:
    """
    Bozor tahlili ostidagi timeframe tugmalari.
    """
    tfs = [("M5", "5m"), ("M15", "15m"), ("H1", "1h"), ("H4", "4h"), ("D1", "1d")]
    row1 = []
    for label, tf in tfs:
        text = f"✅ {label}" if tf == current_tf else label
        row1.append(InlineKeyboardButton(text=text, callback_data=f"ana_tf:{tf}"))

    row2 = [
        InlineKeyboardButton(text="🔄 Yangilash", callback_data=f"ana_refresh:{current_tf}"),
        InlineKeyboardButton(text="🎯 Signal olish", callback_data=f"sig_tf:{current_tf}")
    ]

    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])

def get_calc_keyboard() -> InlineKeyboardMarkup:
    """
    Lot kalkulyatori uchun tezkor depozit va risk tanlash tugmalari.
    """
    row1 = [
        InlineKeyboardButton(text="💵 100$", callback_data="calc_dep:100"),
        InlineKeyboardButton(text="💵 300$", callback_data="calc_dep:300"),
        InlineKeyboardButton(text="💵 500$", callback_data="calc_dep:500"),
    ]
    row2 = [
        InlineKeyboardButton(text="💵 1,000$", callback_data="calc_dep:1000"),
        InlineKeyboardButton(text="💵 2,500$", callback_data="calc_dep:2500"),
        InlineKeyboardButton(text="💵 5,000$", callback_data="calc_dep:5000"),
    ]
    row3 = [
        InlineKeyboardButton(text="Risk 0.5%", callback_data="calc_risk:0.5"),
        InlineKeyboardButton(text="Risk 1.0%", callback_data="calc_risk:1.0"),
        InlineKeyboardButton(text="Risk 2.0%", callback_data="calc_risk:2.0"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3])
