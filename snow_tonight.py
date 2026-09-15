#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snow_tonight.py  --  夕方出発 → 翌日滑走 のためのスキー場判定

今夜から翌朝までの降雪（＝翌朝の新雪）を主スコアにして、行き先を1つ選ぶ。
結果は iPhone で見るための HTML として書き出す。

スキー場マスタは snow-forecast と iSKI のお気に入り登録から起こしたもの。

使い方:
    python snow_tonight.py                    # 今夜出発 → 明日滑走（車で行ける範囲）
    python snow_tonight.py --trip             # 東北の遠征先も含める
    python snow_tonight.py --offset 2         # 明日の夜出発 → あさって滑走
    python snow_tonight.py --area 妙高 白馬
    python snow_tonight.py --max-drive 3      # 片道3時間以内だけ
    python snow_tonight.py --open             # 書き出し後ブラウザで開く
    python snow_tonight.py --nav              # index.html / all.html への切り替えリンクを付ける

朝8時より前に実行したときは、いま明けつつある夜（昨夜17時→今朝8時）の分を出す。

依存: 標準ライブラリのみ
"""

import argparse
import datetime as dt
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

API = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# ---------------------------------------------------------------------------
# スキー場マスタ（snow-forecast + iSKI のお気に入りから作成）
#   top/base : 山頂・山麓標高(m)。雪線高度と比べて雨転リスクを見る
#   wind     : 雪をもたらす850hPa風向の中心(度)と許容幅
#              奥伊吹・福井・奥美濃 = 西〜西北西（JPCZが若狭湾から侵入）
#              白馬・妙高・湯沢     = 北西
#              志賀・野沢・斑尾     = 北北西〜北
#   drive    : 京田辺からの片道所要の目安(時間)。実測に合わせて直してください
#   trip     : True = 車の日帰り圏外。既定では出ない（--trip で合流）
# ---------------------------------------------------------------------------
RESORTS = [
    # --- 滋賀 ---
    dict(name="奥伊吹",           area="滋賀", lat=35.4500, lon=136.4200, top=1230, base=730,  wind=(285, 40), drive=1.5),

    # --- 福井 ---
    dict(name="スキージャム勝山", area="福井", lat=36.0130, lon=136.5600, top=1250, base=600,  wind=(280, 40), drive=2.5),

    # --- 岐阜 ---
    dict(name="高鷲スノーパーク", area="岐阜", lat=35.9175, lon=136.8950, top=1550, base=1050, wind=(285, 40), drive=3.0),
    dict(name="めいほう",         area="岐阜", lat=35.8550, lon=136.9550, top=1600, base=1000, wind=(285, 40), drive=3.2),
    dict(name="白鳥高原",         area="岐阜", lat=35.9200, lon=136.8200, top=1150, base=880,  wind=(285, 40), drive=2.9),

    # --- 石川 ---
    dict(name="白山セイモア",     area="石川", lat=36.2450, lon=136.6500, top=1090, base=760,  wind=(285, 40), drive=3.0),

    # --- 長野 / 白馬 ---
    dict(name="白馬八方尾根",     area="白馬", lat=36.7000, lon=137.8380, top=1831, base=760,  wind=(310, 40), drive=5.0),
    dict(name="白馬五竜",         area="白馬", lat=36.6630, lon=137.8450, top=1676, base=800,  wind=(310, 40), drive=5.0),
    dict(name="Hakuba47",         area="白馬", lat=36.6560, lon=137.8500, top=1616, base=830,  wind=(310, 40), drive=5.0),
    dict(name="白馬岩岳",         area="白馬", lat=36.7200, lon=137.8450, top=1289, base=750,  wind=(310, 40), drive=5.1),
    dict(name="栂池高原",         area="白馬", lat=36.7520, lon=137.8330, top=1704, base=830,  wind=(315, 40), drive=5.1),
    dict(name="白馬コルチナ",     area="白馬", lat=36.7900, lon=137.8200, top=1402, base=800,  wind=(315, 40), drive=5.2),

    # --- 長野 / 北信 ---
    dict(name="野沢温泉",         area="北信", lat=36.9250, lon=138.4500, top=1650, base=565,  wind=(325, 45), drive=5.6),
    dict(name="斑尾高原",         area="北信", lat=36.8750, lon=138.3450, top=1382, base=1000, wind=(325, 45), drive=5.4),
    dict(name="戸隠",             area="北信", lat=36.7550, lon=138.0700, top=1748, base=1200, wind=(320, 45), drive=5.0),
    dict(name="山田牧場",         area="北信", lat=36.7050, lon=138.4100, top=1700, base=1500, wind=(335, 45), drive=5.3),
    dict(name="木島平",           area="北信", lat=36.8700, lon=138.4300, top=1350, base=640,  wind=(325, 45), drive=5.5),

    # --- 長野 / 志賀高原 ---
    dict(name="志賀高原 横手山",  area="志賀", lat=36.6900, lon=138.5200, top=2307, base=1600, wind=(340, 45), drive=5.5),
    dict(name="志賀高原 焼額山",  area="志賀", lat=36.7100, lon=138.4800, top=2009, base=1530, wind=(340, 45), drive=5.4),
    dict(name="志賀高原 寺子屋",  area="志賀", lat=36.7050, lon=138.5100, top=2125, base=1800, wind=(340, 45), drive=5.5),

    # --- 新潟 / 妙高 ---
    dict(name="妙高杉ノ原",       area="妙高", lat=36.8650, lon=138.1280, top=1855, base=745,  wind=(320, 40), drive=5.2),
    dict(name="赤倉観光リゾート", area="妙高", lat=36.8850, lon=138.1680, top=1350, base=1000, wind=(320, 40), drive=5.2),
    dict(name="赤倉温泉",         area="妙高", lat=36.8900, lon=138.1620, top=1300, base=750,  wind=(320, 40), drive=5.2),
    dict(name="池の平温泉",       area="妙高", lat=36.8600, lon=138.1900, top=1500, base=750,  wind=(320, 40), drive=5.3),
    dict(name="ロッテアライ",     area="妙高", lat=37.0130, lon=138.2080, top=1280, base=310,  wind=(320, 40), drive=5.4),

    # --- 新潟 / 湯沢 ---
    dict(name="かぐら",           area="湯沢", lat=36.8670, lon=138.8220, top=1845, base=580,  wind=(315, 40), drive=6.0),
    dict(name="苗場",             area="湯沢", lat=36.7840, lon=138.7950, top=1789, base=900,  wind=(315, 40), drive=6.0),

    # --- 東北・福島（連泊 / 飛行機前提） ---
    dict(name="安比高原",         area="東北", lat=40.0400, lon=140.9600, top=1304, base=500,  wind=(300, 45), drive=None, trip=True),
    dict(name="八幡平パノラマ",   area="東北", lat=40.0000, lon=140.9200, top=1100, base=600,  wind=(300, 45), drive=None, trip=True),
    dict(name="夏油高原",         area="東北", lat=39.1300, lon=140.8500, top=1300, base=500,  wind=(300, 45), drive=None, trip=True),
    dict(name="蔵王温泉",         area="東北", lat=38.1700, lon=140.4000, top=1661, base=780,  wind=(290, 45), drive=None, trip=True),
    dict(name="ネコママウンテン", area="東北", lat=37.5600, lon=139.9700, top=1400, base=1100, wind=(305, 45), drive=None, trip=True),

    # --- 北アルプス（春スキー / 立山黒部アルペンルート） ---
    dict(name="立山 室堂",        area="立山", lat=36.5770, lon=137.5950, top=3003, base=2450, wind=(300, 45), drive=None, trip=True),
]

MODELS = ["jma_seamless", "ecmwf_ifs025", "gfs_seamless"]
NIGHT = (17, 8)   # 当日17時 → 翌8時
DAY = (8, 16)     # 翌8時 → 翌16時
DAY_TRIP_HOURS = 5.5   # これ以内なら夕方出発の日帰り圏（妙高まで）
SNOWLINE_BELOW_FL = 300   # 雪線は0℃高度よりおよそ300m低い
LAPSE = 6.5               # 気温減率(℃/km)。0℃高度が取れないときに山頂気温から推定する
NO_SNOW_CM = 1            # 1位でもこれ未満なら「どこも降らない」表示にする
RAIN_MM = 1               # 夜間の降水がこれ未満なら、雪線が高くても雨の表示はしない
STALE_HOURS = 13          # 定時実行の間隔は最大12時間（4時→16時）。これを超えたら警告
FETCH_TRIES = 3           # Open-Meteo は一時的に接続が切れることがあるので再試行する

# 一覧どうしの切り替えリンク（--nav）。GitHub Pages 上のファイル名
NAV = [
    ("日帰り圏", "index.html"),
    ("東北・立山も含む", "all.html"),
]


def fetch(resorts, hourly, model, days, start=None, end=None):
    params = {
        "latitude": ",".join(f"{r['lat']:.4f}" for r in resorts),
        "longitude": ",".join(f"{r['lon']:.4f}" for r in resorts),
        "elevation": ",".join(str(r["top"]) for r in resorts),
        "hourly": ",".join(hourly),
        "timezone": "Asia/Tokyo",
        "models": model,
    }
    if start:
        url = ARCHIVE
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        url = API
        params["forecast_days"] = str(days)
        params["past_days"] = "1"   # 朝8時前の実行で昨夜17時からの分を取るため

    url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(1, FETCH_TRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as res:
                data = json.loads(res.read().decode())
            return data if isinstance(data, list) else [data]
        except Exception as e:
            print(f"[warn] {model} 取得失敗 ({attempt}/{FETCH_TRIES}): {e}", file=sys.stderr)
            if attempt < FETCH_TRIES:
                time.sleep(5 * attempt)
    return None


def window(times, values, start_dt, end_dt):
    out = []
    for t, v in zip(times, values or []):
        ts = dt.datetime.fromisoformat(t)
        if start_dt <= ts < end_dt and v is not None:
            out.append(v)
    return out


def angle_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def resolve_target(offset, now):
    """滑る日を決める。朝8時前は、いま明けつつある夜の分を見たいので当日を1日目とする"""
    first = now.date() if now.hour < NIGHT[1] else now.date() + dt.timedelta(days=1)
    return first + dt.timedelta(days=offset - 1)


def night_label(target, today):
    if target == today:
        return "昨夜17時から今朝8時まで"
    if target == today + dt.timedelta(days=1):
        return "今夜17時から明朝8時まで"
    prev = target - dt.timedelta(days=1)
    return f"{prev.month}/{prev.day} 17時から{target.month}/{target.day} 8時まで"


def snowline(per_model, order, i, r, start_dt, end_dt):
    """夜間の平均雪線高度(m)。0℃高度はGFSにしか無いことが多いので、あるモデルを順に探す"""
    for m in order:
        h = per_model[m][i]["hourly"]
        fl = window(h["time"], h.get("freezing_level_height"), start_dt, end_dt)
        if fl:
            return sum(fl) / len(fl) - SNOWLINE_BELOW_FL
    for m in order:
        h = per_model[m][i]["hourly"]
        temps = window(h["time"], h.get("temperature_2m"), start_dt, end_dt)
        if temps:
            fl = r["top"] + sum(temps) / len(temps) / LAPSE * 1000
            return fl - SNOWLINE_BELOW_FL
    return None


def wind_ratio(dirs, speeds, favored):
    """雪を運ぶ向きの風が吹いていた時間の割合。強い風が1時間も無ければ None"""
    center, tol = favored
    hits = total = 0
    for d, s in zip(dirs, speeds):
        if s is None or d is None or s < 15:
            continue
        total += 1
        if angle_diff(d, center) <= tol:
            hits += 1
    return hits / total if total else None


def analyse(offset, resorts, on_date=None):
    now = dt.datetime.now()
    target = on_date or resolve_target(offset, now)
    night_start = dt.datetime.combine(target - dt.timedelta(days=1), dt.time(NIGHT[0]))
    night_end = dt.datetime.combine(target, dt.time(NIGHT[1]))
    day_start = dt.datetime.combine(target, dt.time(DAY[0]))
    day_end = dt.datetime.combine(target, dt.time(DAY[1]))
    need = max((target - now.date()).days + 1, 1)
    span = (target - dt.timedelta(days=1), target) if on_date else (None, None)

    surf_vars = ["snowfall", "precipitation", "freezing_level_height", "temperature_2m"]
    pres_vars = ["temperature_850hPa", "wind_direction_850hPa", "wind_speed_850hPa"]

    per_model = {}
    for m in MODELS:
        d = fetch(resorts, surf_vars, m, need, *span)
        if d:
            per_model[m] = d
    if not per_model:
        sys.exit("データを取得できませんでした。ネットワークを確認してください。")
    pres = fetch(resorts, pres_vars, "gfs_seamless", need, *span)

    main = "jma_seamless" if "jma_seamless" in per_model else list(per_model)[0]
    order = [main] + [m for m in per_model if m != main]
    rows = []
    for i, r in enumerate(resorts):
        by_model = {}
        for m, data in per_model.items():
            hh = data[i]["hourly"]
            by_model[m] = sum(window(hh["time"], hh.get("snowfall"), night_start, night_end))
        h = per_model[main][i]["hourly"]
        day = sum(window(h["time"], h.get("snowfall"), day_start, day_end))
        precip = sum(window(h["time"], h.get("precipitation"), night_start, night_end))

        sl = snowline(per_model, order, i, r, night_start, night_end)
        rain = precip >= RAIN_MM and sl is not None and sl > (r["top"] + r["base"]) / 2

        t850_min = wr = None
        if pres:
            ph = pres[i]["hourly"]
            pt = ph["time"]
            t850 = window(pt, ph.get("temperature_850hPa"), night_start, day_end)
            wd = window(pt, ph.get("wind_direction_850hPa"), night_start, day_end)
            ws = window(pt, ph.get("wind_speed_850hPa"), night_start, day_end)
            t850_min = min(t850) if t850 else None
            wr = wind_ratio(wd, ws, r["wind"])

        rows.append(dict(
            name=r["name"], area=r["area"], drive=r.get("drive"),
            trip=r.get("trip", False), top=r["top"], base=r["base"],
            night=by_model[main], day=day, snowline=sl, rain=rain,
            t850=t850_min, wind_ratio=wr, has_pres=pres is not None,
            by_model=by_model,
        ))
    # 表示している主モデルの cm で並べる。同じ cm なら雨の心配が無いほう → 車の時間が短いほう
    rows.sort(key=lambda x: (-round(x["night"]), x["rain"],
                             x["drive"] if x["drive"] is not None else 99))
    return rows, target, main, list(per_model)


def access(r):
    if r["drive"] is None:
        return "遠征"
    if r["drive"] > DAY_TRIP_HOURS:
        return f"車{r['drive']:.1f}h・日帰り圏外"
    return f"車{r['drive']:.1f}h"


# ---------------------------------------------------------------------------
# HTML 出力
# ---------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#131A26;color:#EDF2F7;
 font-family:"Hiragino Sans","Yu Gothic UI","Noto Sans JP",system-ui,sans-serif;
 -webkit-text-size-adjust:100%;padding:20px 16px 48px;line-height:1.5}
.wrap{max-width:620px;margin:0 auto}
.stamp{color:#7C8AA0;font-size:13px}
.stamp b{color:#EDF2F7;font-weight:600}
.nav{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:10px;font-size:13px}
.nav a{color:#A7B4C6}
.nav a[aria-current]{color:#EDF2F7;font-weight:600;text-decoration:none}
.stale{margin-top:14px;padding:10px 12px;border:1px solid #E2664F;border-radius:3px;
 color:#F3B3A6;font-size:13px}
.hero{margin:22px 0 8px;padding:22px 20px 20px;background:#1C2534;
 border-left:4px solid #FFB454;border-radius:3px}
.hero .where{font-size:22px;font-weight:700}
.hero .sub{color:#7C8AA0;font-size:13px;margin-top:5px}
.hero .cap{font-size:13px;color:#A7B4C6;margin-top:14px}
.hero.empty{border-left-color:#5B6B82}
.hero.empty .where{font-size:18px}
.list{margin-top:26px;border-top:1px solid #2A3546}
.row{padding:14px 2px 13px;border-bottom:1px solid #2A3546}
.row .head{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.row .nm{font-size:16px;font-weight:600}
.row .where{color:#7C8AA0;font-size:12px;flex:none}
.meta{color:#7C8AA0;font-size:12px;margin-top:8px}
.hero .meta{margin-top:10px}
.models{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:9px}
.models i{display:block;font-style:normal;font-size:12px;color:#7C8AA0;letter-spacing:.02em}
.models b{font-size:30px;font-weight:700;color:#C7D3E4;font-variant-numeric:tabular-nums}
.models u{font-size:12px;font-weight:600;text-decoration:none;color:#7C8AA0;margin-left:2px}
.models .hi b{color:#8FB4E8}
.models .na b{color:#4A5870}
.models s{display:block;text-decoration:none;font-size:11px;color:#E2664F}
.hero .models{margin-top:16px}
.hero .models i{font-size:13px}
.hero .models b{font-size:42px;color:#EDF2F7}
.hero .models .hi b{color:#FFB454}
.hero .models .na b{color:#4A5870}
.hero .models u{font-size:14px}
.warn{color:#E2664F}
.rain-note{color:#E2664F;font-size:12px}
.bar{height:3px;background:#2A3546;border-radius:2px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;background:#5B86C4}
h2{font-size:13px;font-weight:600;color:#7C8AA0;margin:30px 0 10px}
.note{color:#7C8AA0;font-size:12.5px;line-height:1.75;margin-top:8px}
.links{margin-top:26px;display:flex;flex-wrap:wrap;gap:8px}
.links a{color:#A7B4C6;font-size:13px;text-decoration:none;
 border:1px solid #2A3546;border-radius:3px;padding:7px 11px}
.links a:focus-visible,.nav a:focus-visible{outline:2px solid #FFB454;outline-offset:2px}
"""

# 開いた時点で更新からの経過時間を出し、止まっていたら警告する
SCRIPT = """<script>
(function(){
  var g = new Date(document.body.getAttribute("data-generated"));
  var h = (Date.now() - g.getTime()) / 36e5;
  if (!isFinite(h)) return;
  document.getElementById("age").textContent =
    h < 1 ? "（1時間以内）" : "（" + Math.floor(h) + "時間前）";
  if (h <= __STALE__) return;
  var m = new Date().getMonth() + 1;
  var s = document.getElementById("stale");
  s.textContent = (m >= 6 && m <= 10)
    ? "シーズン外（6〜10月）は自動更新を止めています。表示は最後に更新したときの予報です。"
    : "最終更新から" + Math.floor(h) + "時間たっています。自動更新が止まっている可能性があります。";
  s.hidden = false;
})();
</script>""".replace("__STALE__", str(STALE_HOURS))

BOOKMARKS = [
    ("Windy 新雪", "https://www.windy.com/ja/-%E6%96%B0%E9%9B%AA-snowAccu?snowAccu,35.954,137.867,8"),
    ("ウェザーニュース", "https://weathernews.jp/ski/search_map.html"),
    ("snow-forecast", "https://www.snow-forecast.com/my"),
    ("iHighway 中日本", "https://www.c-ihighway.jp/pcsite/map?area=area05"),
    ("除雪ナビ", "https://snowcar.vpis.jp/main.php?pageid=5&pagedir=2&pageblk=50216&mode=#d50216"),
]


MODEL_LABEL = {
    "jma_seamless": "気象庁",
    "ecmwf_ifs025": "ECMWF",
    "gfs_seamless": "GFS",
}


def model_strip(r):
    parts = []
    for key in MODELS:
        label = MODEL_LABEL.get(key, key)
        if key not in r["by_model"]:
            parts.append(f'<div class="na"><i>{label}</i><b>—</b><s>取得失敗</s></div>')
            continue
        v = r["by_model"][key]
        cls = ' class="hi"' if v >= 5 else ""
        parts.append(
            f'<div{cls}><i>{label}</i>'
            f'<b>{v:.0f}</b><u>cm</u></div>'
        )
    return f'<div class="models">{"".join(parts)}</div>'


def meta(r):
    t850 = f'{r["t850"]:.0f}℃' if r["t850"] is not None else "—"
    if not r["has_pres"]:
        wind = "風向—"
    elif r["wind_ratio"] is None:
        wind = "風弱"
    else:
        wind = f'風向{r["wind_ratio"]*100:.0f}%'
    note = ""
    if r["rain"]:
        note = f'　<span class="rain-note">雪線{r["snowline"]:.0f}m・山麓は雨</span>'
    return f'<div class="meta">日中{r["day"]:.0f}cm　850hPa {t850}　{wind}{note}</div>'


def nav_html(path):
    here = os.path.basename(path)
    parts = []
    for label, href in NAV:
        if href == here:
            parts.append(f'<a aria-current="page">{html.escape(label)}</a>')
        else:
            parts.append(f'<a href="{href}">{html.escape(label)}</a>')
    return f'<nav class="nav">{"".join(parts)}</nav>'


def render(rows, target, main, available, path, nav=False):
    now = dt.datetime.now()
    d = target.strftime("%m月%d日")
    wd = "月火水木金土日"[target.weekday()]
    top = rows[0]
    mx = max((r["night"] for r in rows), default=1) or 1
    period = night_label(target, now.date())

    def line(r):
        return (
            f'<div class="row">'
            f'<div class="head">'
            f'<div class="nm">{html.escape(r["name"])}</div>'
            f'<div class="where">{r["area"]}・{access(r)}</div>'
            f'</div>'
            f'{model_strip(r)}'
            f'{meta(r)}'
            f'<div class="bar"><i style="width:{min(r["night"]/mx*100,100):.0f}%"></i></div>'
            f'</div>'
        )

    if round(top["night"]) < NO_SNOW_CM:
        hero = f"""<div class="hero empty">
  <div class="where">どのスキー場も新雪は1cm未満の見込み</div>
  <div class="cap">{period}に<b>新しく降る</b>量で、{MODEL_LABEL.get(main, main)}モデルが1cm以上を出したスキー場がありません。</div>
</div>"""
        body = "".join(line(r) for r in rows)
    else:
        thin = "　まとまった新雪ではありません。" if top["night"] < 5 else ""
        hero = f"""<div class="hero">
  <div class="where">{html.escape(top["name"])}</div>
  <div class="sub">{top["area"]}　{access(top)}</div>
  {model_strip(top)}
  {meta(top)}
  <div class="cap">{period}に<b>新しく降る</b>量。日中さらに{top["day"]:.0f}cm。{thin}</div>
</div>"""
        body = "".join(line(r) for r in rows[1:])

    missing = [MODEL_LABEL.get(m, m) for m in MODELS if m not in available]
    warn = f'　<span class="warn">{"・".join(missing)}は取得失敗</span>' if missing else ""
    links = "".join(f'<a href="{u}">{html.escape(n)}</a>' for n, u in BOOKMARKS)
    generated = now.astimezone().isoformat(timespec="minutes")

    doc = f"""<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>翌朝の新雪 {d}</title><style>{CSS}</style></head><body data-generated="{generated}"><div class="wrap">
<p class="stamp">{d}（{wd}）朝の<b>新雪</b>見込み　<b>{now:%m/%d %H:%M} 更新</b><span id="age"></span>　順位は{MODEL_LABEL.get(main, main)}モデル基準{warn}</p>
{nav_html(path) if nav else ""}
<div class="stale" id="stale" hidden></div>

{hero}

<div class="list">{body}</div>

<h2>読み方</h2>
<p class="note">
数字は<b>新雪</b>の量で、翌朝ファーストトラックで踏める深さの目安です。
地面に積もっている総量（積雪深）は出していません。そちらは下のウェザーニュースか各スキー場の発表を見てください。<br>
<b>気象庁・ECMWF・GFSの3つの数値予報モデルが、それぞれ何cmと言っているかを並べています。</b>
列の位置は全行で揃えてあるので、縦に目を走らせればスキー場どうしを比べられます。
青い数字は5cm以上を予想したモデルで、<b>3つとも青い日は当たりの確度が高い</b>。
1つだけ突出している日は、そのモデルだけが違う絵を描いているので様子見が無難です。
天気予報サイトごとに数字が食い違うのは、どのモデルを使っているかの差です。ここを直接見れば、サイトを見比べる手間が省けます。
ただし3つは同じ観測データから出発しているので、揃って外れることもあります。<br>
並び順は気象庁モデルの値（cm）で決めています。日本の地形を扱う解像度がいちばん高いためですが、
どのモデルが当たりやすいかは検証できていません。同じcmなら、雨の心配が無いほう、車の時間が短いほうを上にしています。<br>
新雪の量は、水量から一定の係数で換算した値です。気温が低く乾いた雪ほど実際にはもっと嵩が出るので、
<b>本当のパウダーの日はこの数字より深くなります</b>。絶対値より、候補どうしの大小とモデルの揃い方で判断してください。<br>
赤字は、夜間の雪線（0℃になる高さの約300m下）が山頂と山麓の中間より上にあり、山麓が雨になる可能性が高いことを示します。
風向%は、そのスキー場に雪を運ぶ風向に850hPaの風が入っている時間の割合。「風弱」は判定できるほどの風が吹いていないという意味です。<br>
数字が近い候補が並んだら、車の時間が短いほうを選ぶのが現実的です。
夜間降雪が多い日は道路も荒れるので、出発前に下の除雪ナビとiHighwayを必ず見てください。
</p>

<div class="links">{links}</div>
</div>
{SCRIPT}
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=1, help="何日後に滑るか（既定=1: 明日。朝8時前は今日）")
    ap.add_argument("--area", nargs="*", help="滋賀 福井 岐阜 石川 白馬 北信 志賀 妙高 湯沢 東北 立山")
    ap.add_argument("--max-drive", type=float)
    ap.add_argument("--trip", action="store_true", help="東北など車の日帰り圏外も含める")
    ap.add_argument("--today", action="store_true", help=f"片道{DAY_TRIP_HOURS}時間以内の日帰り圏だけ")
    ap.add_argument("--date", help="過去日で検証 (YYYY-MM-DD)。--offset は無視される")
    ap.add_argument("--out", default="ranking.html")
    ap.add_argument("--nav", action="store_true", help="index.html / all.html への切り替えリンクを付ける")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    rs = RESORTS
    if args.area:
        rs = [r for r in rs if r["area"] in args.area]
    elif not args.trip:
        rs = [r for r in rs if not r.get("trip")]
    if args.today:
        rs = [r for r in rs if r.get("drive") is not None and r["drive"] <= DAY_TRIP_HOURS]
    if args.max_drive:
        rs = [r for r in rs if r.get("drive") is not None and r["drive"] <= args.max_drive]
    if not rs:
        sys.exit("条件に合うスキー場がありません")

    on_date = dt.date.fromisoformat(args.date) if args.date else None
    rows, target, main_model, available = analyse(args.offset, rs, on_date)
    render(rows, target, main_model, available, args.out, nav=args.nav)

    label = "【過去日で検証】" if on_date else ""
    print(f"\n{label}{target:%Y/%m/%d} 朝の新雪見込み（{main_model} / {len(available)}モデル照合 / {len(rs)}スキー場）\n")
    for i, r in enumerate(rows[:10], 1):
        mark = f" ※雪線{r['snowline']:.0f}m・山麓は雨" if r["rain"] else ""
        ms = "  ".join(f"{MODEL_LABEL.get(k, k)}{r['by_model'][k]:4.1f}"
                       for k in MODELS if k in r["by_model"])
        print(f"{i:2}. {r['name']:<14} 新雪{r['night']:5.1f}cm  日中{r['day']:5.1f}cm  "
              f"[{ms}]  {access(r)}{mark}")
    path = os.path.abspath(args.out)
    print(f"\nHTML: {path}\n")
    if args.open:
        webbrowser.open("file://" + path)


if __name__ == "__main__":
    main()
