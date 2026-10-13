"""Registry of factors: how each raw column becomes a 0–1 percentile (1 = better)."""
FACTORS = {
    "metro_min":     {"label": "Пешком до метро", "unit": "мин", "better": "low",  "period": "OSM, 2026-10"},
    "crime_rate":    {"label": "Уличная преступность (кражи, грабежи, хулиганство)", "unit": "на 1000 жит./год", "better": "low", "period": "gis.kgp.kz 2023–2025 / Kontur 2023"},
    "pm25_winter":   {"label": "PM2.5 зимой", "unit": "мкг/м³", "better": "low", "period": "airkaz.org, зимы 2017–2020"},
    "pm25_recent":   {"label": "PM2.5 за последние 7 дней", "unit": "мкг/м³", "better": "low", "period": "AirGradient + airkaz, часовые снимки", "default": 0, "fact": True},
    "car_min":       {"label": "На авто до моих точек, будни 8:30", "unit": "мин", "better": "low", "period": "2GIS"},
    "pt_min":        {"label": "Общественным транспортом до моих точек, будни 8:30", "unit": "мин", "better": "low", "period": "2GIS"},
    "car_ev_min":    {"label": "На авто из моих точек домой, будни 18:30", "unit": "мин", "better": "low", "period": "2GIS"},
    "transit_proxy": {"label": "Маршрутов автобуса/троллейбуса в 400 м", "unit": "маршр.", "better": "high", "period": "OSM, 2026-10"},
    "cat15":         {"label": "Инфраструктура в 1 км", "unit": "из 6", "better": "high", "period": "OSM, 2026-10"},
    # facts: shown in the card, weight 0 unless the user ticks them
    "dtp_300m":      {"label": "ДТП в 300 м за 2023–2025", "unit": "ДТП", "better": "low", "period": "gis.kgp.kz", "default": 0, "fact": True},
    "price_m2_zhk":  {"label": "Цена м² в ЖК рядом", "unit": "₸/м²", "better": "low", "period": "krisha.kz ЖК, 2026-10-13", "default": 0, "fact": True},
    "price_m2_hex":  {"label": "Цена м² по объявлениям рядом", "unit": "₸/м²", "better": "low", "period": "krisha.kz, 2026-10-13", "default": 0, "fact": True},
}
