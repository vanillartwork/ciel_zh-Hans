# -*- coding: utf-8 -*-
"""Officially published Chinese names, harvested from Koei Tecmo Taiwan.

Source: https://www.gamecity.com.tw/ciel/offline/  (KOEI TECMO Taiwan GAMECITY,
the publisher own site for Ciel nosurge offline) -- character pages cha01-cha16
and the glossary pages glo01-glo10.  The game itself was never localised, so
this promotional material is the only publisher-sanctioned Chinese wording that
exists.  It is Traditional Chinese; zh_cn below is the Simplified conversion.

Columns: in-game Japanese form, official Traditional, Simplified, kind
"""

OFFICIAL = [
    # ---- characters (cha01-cha16) ----
    ("イオン",         "依恩",           "依恩",           "character"),
    ("イオナサル・ククルル・プリシェール", "依歐娜薩魯・庫庫魯魯・普立薛爾",
                                        "依欧娜萨鲁・库库鲁鲁・普立薛尔", "character"),
    ("カノン",         "卡諾",           "卡诺",           "character"),
    ("カノイール・ククルル・プリシェール", "卡諾伊爾・酷酷魯魯・普立薛爾",
                                        "卡诺伊尔・酷酷鲁鲁・普立薛尔", "character"),
    ("ネイ",          "妮伊",           "妮伊",           "character"),
    ("ねりこ",         "妮莉庫",          "妮莉库",          "character"),
    ("キャス",         "凱斯",           "凯斯",           "character"),
    ("キャスティ",      "凱斯蒂",          "凯斯蒂",          "character"),
    ("ター坊",         "阿達",           "阿达",           "character"),
    ("プラム",         "布拉姆",          "布拉姆",          "character"),
    ("テレフンケン",     "泰雷芬肯",         "泰雷芬肯",         "character"),
    ("レナルル",        "蕾娜露露",         "蕾娜露露",         "character"),
    ("白鷹",          "白鷹",           "白鹰",           "character"),
    ("サーリ",         "莎麗",           "莎丽",           "character"),
    ("ジル",          "吉魯",           "吉鲁",           "character"),
    ("クラケット",      "庫拉肯特",         "库拉肯特",         "character"),
    ("リーヴェルト",     "利維爾特",         "利维尔特",         "character"),
    ("ネプツール",      "尼普楚爾",         "尼普楚尔",         "character"),
    ("グレイコフ",      "古雷柯夫",         "古雷柯夫",         "character"),
    ("ウンドゥ",        "溫多",           "温多",           "character"),
    ("ニュロキー",      "喵洛基",          "喵洛基",          "character"),
    # cha14 gives no Japanese name, but its description (the girl at the lab
    # whose surface consciousness is used as the Cielnotron OS Reon-4213)
    # matches ネロ exactly -- the game text says so outright:
    # "レオンOSと呼ばれるものの正体は生身の少女、ネロ".
    ("ネロ",          "妮諾",           "妮诺",           "character"),

    # ---- world / glossary (glo01-glo10) ----
    ("ラシェーラ",      "拉榭拉",          "拉榭拉",          "term"),
    ("コロン",         "克隆",           "克隆",           "term"),
    ("コロン・フォーシーズン", "克隆四季",       "克隆四季",         "term"),
    ("シャール",        "夏爾",           "夏尔",           "term"),
    ("シェルノトロン",    "榭魯諾特倫",        "榭鲁诺特伦",        "term"),
    ("シェル",         "榭魯",           "榭鲁",           "term"),
    ("ベゼル",         "貝捷爾",          "贝捷尔",          "term"),
    ("ソレイル",        "太陽號",          "太阳号",          "term"),
    ("ジェノム",        "傑諾姆",          "杰诺姆",          "term"),
    ("ジェノメトリクス",   "夢世界",          "梦世界",          "term"),
    ("ジェノミライ",     "傑諾米萊伊",        "杰诺米莱伊",        "term"),
    ("アルメティカ",     "阿爾梅堤嘉",        "阿尔梅堤嘉",        "term"),
    ("ウェーブバースト",   "波動爆炸",         "波动爆炸",         "term"),
    ("ネプトロン",      "尼普特倫",         "尼普特伦",         "term"),
    ("クオンタイズ",     "庫翁泰茲",         "库翁泰兹",         "term"),
    ("Tz波",         "Tz波",          "Tz波",          "term"),
    ("天文",          "天文",           "天文",           "term"),
    ("地文",          "地文",           "地文",           "term"),
    ("詩魔法",         "詩魔法",          "诗魔法",          "term"),
    ("同調",          "同調",           "同调",           "term"),
    ("皇女",          "皇女",           "皇女",           "term"),
    ("皇帝",          "皇帝",           "皇帝",           "term"),
    ("皇位継承の儀",     "皇位繼承儀式",       "皇位继承仪式",       "term"),
    ("万寿沙羅",       "萬壽沙羅",         "万寿沙罗",         "term"),
    ("グランフェニックス計画", "大鳳凰計劃",      "大凤凰计划",        "term"),
    ("縦貫坑道",       "縱貫坑道",         "纵贯坑道",         "term"),
    ("波動科学",       "波動科學",         "波动科学",         "term"),
    ("ダイバー",       "潛行者",          "潜行者",          "term"),
    ("ウタヒメ",       "詩姫",           "诗姬",           "term"),
    ("クレイドル",      "支架",           "支架",           "term"),
    ("ワイヤーシップ",    "線導船",          "线导船",          "term"),
    ("パレス・ニュロキール", "喵洛基魯・王宮",     "喵洛基鲁・王宫",      "term"),
    ("ぱれす・にゅろきーる", "喵洛基魯・王宮",     "喵洛基鲁・王宫",      "term"),
    # The game writes this mascot in hiragana in item data; the katakana-only
    # glossary harvest missed it, so the first pass invented 纽罗基.
    ("にゅろきー",      "喵洛基",          "喵洛基",          "term"),
    ("ぱれす",         "王宮",           "王宫",           "term"),
    ("G2トロン",      "G2特倫",         "G2特伦",         "term"),
    ("ジェノメトリック・カソード", "傑諾梅特利庫・陰極", "杰诺梅特利库・阴极",  "term"),
    ("7次元俯瞰理論",    "7次元俯瞰理論",      "7次元俯瞰理论",      "term"),
    ("俯瞰視点",       "俯瞰視點",         "俯瞰视点",         "term"),
    ("大法要",        "大法要",          "大法要",          "term"),
    ("ルル",         "縷縷",           "缕缕",           "term"),
    # transcribed from the same glossary pages, missed on the first pass
    ("パークパスニュロン", "主題樂園護照紐倫",    "主题乐园护照纽伦",     "term"),
    ("ネプトロンタワー",  "尼普特倫塔",        "尼普特伦塔",        "term"),
    ("アルメティカ図書館", "阿爾梅堤嘉圖書館",    "阿尔梅堤嘉图书馆",     "term"),
    ("ジェノミライパンデミック", "傑諾米萊伊瘟疫", "杰诺米莱伊瘟疫",      "term"),
    ("クオリア中心",    "感質中心",         "感质中心",         "term"),
    ("地文調停十二支",   "地文調停十二支",      "地文调停十二支",      "term"),
    ("PLASMA機密情報局", "PLASMA機密情報局", "PLASMA机密情报局",  "term"),
]

# Titles, for reference -- NOT auto-applied anywhere.
TITLES = [
    ("シェルノサージュ ～失われた星へ捧ぐ詩～",
     "Ciel nosurge～獻給失落之星的詩篇",
     "Ciel nosurge～献给失落之星的诗篇",
     "KOEI TECMO Taiwan official site title"),
    ("シェルノサージュ",
     "靜籟之空",
     "静籁之空",
     "used by Bahamut / Wikipedia, NOT the publisher official title"),
]
