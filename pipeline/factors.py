"""Registry of factors: how each raw column becomes a 0–1 percentile (1 = better)."""
FACTORS = {
    "metro_min":     {"label": "Пешком до метро", "unit": "мин", "better": "low",  "period": "OSM, 2026-10"},
    "crime_rate":    {"label": "Преступность на жильё", "unit": "случаев/га жилья·год", "better": "low", "period": "gis.kgp.kz, 2023–2025"},
    "pm25_winter":   {"label": "PM2.5 зимой", "unit": "мкг/м³", "better": "low", "period": "airkaz.org, зимы 2017–2020"},
    "car_min":       {"label": "На авто до моих точек, 8:30", "unit": "мин", "better": "low", "period": "2GIS"},
    "pt_min":        {"label": "На ОТ до моих точек, 8:30", "unit": "мин", "better": "low", "period": "2GIS"},
    "transit_proxy": {"label": "Маршрутов ОТ рядом", "unit": "шт в 400 м", "better": "high", "period": "OSM, 2026-10"},
    "cat15":         {"label": "Инфраструктура в 1 км", "unit": "категорий из 6", "better": "high", "period": "OSM, 2026-10"},
}
