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

依存: 標準ライブラリのみ
"""

import argparse
import datetime as dt
import html
import json
import os
import sys
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

    url = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as res:
            data = json.loads(res.read().decode())
    except Exception as e:
        print(f"[warn] {model} 取得失敗: {e}", file=sys.stderr)
        return None
    return data if isinstance(data, list) else [data]


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


def quality_factor(fl_vals, top, base):
    if not fl_vals:
        return 0.8, None
    fl = sum(fl_vals) / len(fl_vals)
    if fl <= base:
        return 1.0, fl
    if fl >= top:
        return 0.15, fl
    return 0.15 + 0.85 * (top - fl) / max(top - base, 1), fl


def cold_factor(t850):
    if not t850:
        return 1.0, None
    t = min(t850)
    if t <= -12:
        return 1.20, t
    if t <= -9:
        return 1.10, t
    if t <= -6:
        return 1.00, t
    return 0.85, t


def wind_factor(dirs, speeds, favored):
    center, tol = favored
    hits = total = 0
    for d, s in zip(dirs, speeds):
        if s is None or d is None or s < 15:
            continue
        total += 1
        if angle_diff(d, center) <= tol:
            hits += 1
    if total == 0:
        return 1.0, 0.0
    r = hits / total
    return 1.0 + 0.30 * r, r


def analyse(offset, resorts, on_date=None):
    today = dt.date.today()
    target = on_date or (today + dt.timedelta(days=offset))
    night_start = dt.datetime.combine(target - dt.timedelta(days=1), dt.time(NIGHT[0]))
    night_end = dt.datetime.combine(target, dt.time(NIGHT[1]))
    day_start = dt.datetime.combine(target, dt.time(DAY[0]))
    day_end = dt.datetime.combine(target, dt.time(DAY[1]))
    need = offset + 2
    span = (target - dt.timedelta(days=1), target) if on_date else (None, None)

    surf_vars = ["snowfall", "freezing_level_height", "temperature_2m"]
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
    rows = []
    for i, r in enumerate(resorts):
        h = per_model[main][i]["hourly"]
        t = h["time"]
        night = sum(window(t, h.get("snowfall"), night_start, night_end))
        day = sum(window(t, h.get("snowfall"), day_start, day_end))
        fl = window(t, h.get("freezing_level_height"), day_start, day_end)
        q, fl_mean = quality_factor(fl, r["top"], r["base"])

        t850 = wd = ws = []
        if pres:
            ph = pres[i]["hourly"]
            pt = ph["time"]
            t850 = window(pt, ph.get("temperature_850hPa"), night_start, day_end)
            wd = window(pt, ph.get("wind_direction_850hPa"), night_start, day_end)
            ws = window(pt, ph.get("wind_speed_850hPa"), night_start, day_end)
        c, t850_min = cold_factor(t850)
        wf, wr = wind_factor(wd, ws, r["wind"])

        agree = 0
        for m, data in per_model.items():
            hh = data[i]["hourly"]
            if sum(window(hh["time"], hh.get("snowfall"), night_start, night_end)) >= 5:
                agree += 1

        rows.append(dict(
            name=r["name"], area=r["area"], drive=r.get("drive"),
            trip=r.get("trip", False), top=r["top"], base=r["base"],
            night=night, day=day, fl=fl_mean, t850=t850_min,
            wind_ratio=wr, quality=q,
            score=min(night, 50.0) * q * c * wf,
            agree=agree, models=len(per_model),
        ))
    rows.sort(key=lambda x: -x["score"])
    return rows, target, main, len(per_model)


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
.hero{margin:22px 0 8px;padding:22px 20px 20px;background:#1C2534;
 border-left:4px solid #FFB454;border-radius:3px}
.hero .where{font-size:21px;font-weight:700}
.hero .sub{color:#7C8AA0;font-size:13px;margin-top:5px}
.hero .cm{font-size:68px;font-weight:800;line-height:1;margin-top:14px;
 color:#FFB454;font-variant-numeric:tabular-nums}
.hero .cm span{font-size:22px;font-weight:600;margin-left:4px}
.hero .cap{font-size:13px;color:#A7B4C6;margin-top:6px}
.list{margin-top:26px;border-top:1px solid #2A3546}
.row{padding:13px 2px;border-bottom:1px solid #2A3546}
.row .head{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.row .nm{font-size:15px;font-weight:600}
.row .meta{color:#7C8AA0;font-size:12px;margin-top:3px}
.row .num{flex:none;font-size:27px;font-weight:700;font-variant-numeric:tabular-nums}
.row .num u{font-size:12px;font-weight:600;text-decoration:none;color:#7C8AA0;margin-left:2px}
.rain{color:#E2664F}
.rain-note{color:#E2664F;font-size:12px}
.bar{height:3px;background:#2A3546;border-radius:2px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:#5B86C4}
h2{font-size:13px;font-weight:600;color:#7C8AA0;margin:30px 0 10px}
.note{color:#7C8AA0;font-size:12.5px;line-height:1.75;margin-top:8px}
.links{margin-top:26px;display:flex;flex-wrap:wrap;gap:8px}
.links a{color:#A7B4C6;font-size:13px;text-decoration:none;
 border:1px solid #2A3546;border-radius:3px;padding:7px 11px}
.links a:focus-visible{outline:2px solid #FFB454;outline-offset:2px}
"""

BOOKMARKS = [
    ("Windy 新雪", "https://www.windy.com/ja/-%E6%96%B0%E9%9B%AA-snowAccu?snowAccu,35.954,137.867,8"),
    ("ウェザーニュース", "https://weathernews.jp/ski/search_map.html"),
    ("snow-forecast", "https://www.snow-forecast.com/my"),
    ("iHighway 中日本", "https://www.c-ihighway.jp/pcsite/map?area=area05"),
    ("除雪ナビ", "https://snowcar.vpis.jp/main.php?pageid=5&pagedir=2&pageblk=50216&mode=#d50216"),
]


def render(rows, target, model, nmodels, path):
    now = dt.datetime.now().strftime("%m/%d %H:%M")
    d = target.strftime("%m月%d日")
    wd = "月火水木金土日"[target.weekday()]
    top = rows[0]
    mx = max((r["night"] for r in rows), default=1) or 1

    def line(r):
        rain = r["quality"] < 0.5
        cls = " rain" if rain else ""
        note = ""
        if rain and r["fl"]:
            note = f'　<span class="rain-note">雪線{r["fl"]:.0f}m・山麓は雨</span>'
        t850 = f'{r["t850"]:.0f}℃' if r["t850"] is not None else "—"
        return (
            f'<div class="row">'
            f'<div class="head">'
            f'<div class="nm">{html.escape(r["name"])}</div>'
            f'<div class="num{cls}">{r["night"]:.0f}<u>cm</u></div>'
            f'</div>'
            f'<div class="meta">{r["area"]}・{access(r)}　'
            f'日中{r["day"]:.0f}cm　850hPa {t850}　'
            f'風向{r["wind_ratio"]*100:.0f}%　一致{r["agree"]}/{r["models"]}{note}</div>'
            f'<div class="bar"><i style="width:{min(r["night"]/mx*100,100):.0f}%"></i></div>'
            f'</div>'
        )

    links = "".join(f'<a href="{u}">{html.escape(n)}</a>' for n, u in BOOKMARKS)
    body = "".join(line(r) for r in rows[1:])

    doc = f"""<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>翌朝の新雪 {d}</title><style>{CSS}</style></head><body><div class="wrap">
<p class="stamp">{d}（{wd}）朝の<b>新雪</b>見込み　<b>{now} 更新</b>　{model} / {nmodels}モデル照合</p>

<div class="hero">
  <div class="where">{html.escape(top["name"])}</div>
  <div class="sub">{top["area"]}　{access(top)}</div>
  <div class="cm">{top["night"]:.0f}<span>cm</span></div>
  <div class="cap">今夜17時から明朝8時までに<b>新しく降る</b>量。日中さらに{top["day"]:.0f}cm。
  {top["models"]}モデル中{top["agree"]}つが一致。</div>
</div>

<div class="list">{body}</div>

<h2>読み方</h2>
<p class="note">
大きい数字は<b>新雪</b>の量で、翌朝ファーストトラックで踏める深さの目安です。
地面に積もっている総量（積雪深）は出していません。そちらは下のウェザーニュースか各スキー場の発表を見てください。<br>
新雪の量は、水量から一定の係数で換算した値です。気温が低く乾いた雪ほど実際にはもっと嵩が出るので、
<b>本当のパウダーの日はこの数字より深くなります</b>。絶対値より、候補どうしの大小と一致数で判断してください。<br>
赤字は雪線が山腹より上にあり、山麓が雨になる可能性が高いことを示します。
風向%は、そのスキー場に雪を運ぶ風向に850hPaの風が入っている時間の割合。
一致は、夜間5cm以上を予想したモデルの数で、<b>3つ揃った日は当たりの確度が高い</b>。<br>
数字が近い候補が並んだら、車の時間が短いほうを選ぶのが現実的です。
夜間降雪が多い日は道路も荒れるので、出発前に下の除雪ナビとiHighwayを必ず見てください。
</p>

<div class="links">{links}</div>
</div></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=1, help="何日後に滑るか（既定=1: 明日）")
    ap.add_argument("--area", nargs="*", help="滋賀 福井 岐阜 石川 白馬 北信 志賀 妙高 湯沢 東北 立山")
    ap.add_argument("--max-drive", type=float)
    ap.add_argument("--trip", action="store_true", help="東北など車の日帰り圏外も含める")
    ap.add_argument("--today", action="store_true", help=f"片道{DAY_TRIP_HOURS}時間以内の日帰り圏だけ")
    ap.add_argument("--date", help="過去日で検証 (YYYY-MM-DD)。--offset は無視される")
    ap.add_argument("--out", default="ranking.html")
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
    rows, target, model, n = analyse(args.offset, rs, on_date)
    render(rows, target, model, n, args.out)

    label = "【過去日で検証】" if on_date else ""
    print(f"\n{label}{target:%Y/%m/%d} 朝の新雪見込み（{model} / {n}モデル照合 / {len(rs)}スキー場）\n")
    for i, r in enumerate(rows[:10], 1):
        mark = " ※山麓は雨" if r["quality"] < 0.5 else ""
        print(f"{i:2}. {r['name']:<14} 新雪{r['night']:5.1f}cm  日中{r['day']:5.1f}cm  "
              f"{access(r):<7} 一致{r['agree']}/{r['models']}{mark}")
    path = os.path.abspath(args.out)
    print(f"\nHTML: {path}\n")
    if args.open:
        webbrowser.open("file://" + path)


if __name__ == "__main__":
    main()
