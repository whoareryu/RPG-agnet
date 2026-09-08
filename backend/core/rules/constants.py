"""밸런스 수치의 단일 출처. 근거는 설계 문서 13장.

다른 곳에 리터럴을 쓰지 않는다. 튠할 때 여기만 바꾼다.
"""

# ─── 능력치 (설계 §4.2·§13) ────────────────────────────────────────────
STAT_MIN = 1
STAT_MAX = 20
STAT_BASE = 8
FREE_POINTS = 18  # 한 능력치 몰빵(8+12=20)이 가능해야 "몰빵 실험"이 성립한다

# ─── 성향 (설계 §4.5) ─────────────────────────────────────────────────
DISPOSITION_MIN = -100
DISPOSITION_MAX = 100

# ─── 신체 (설계 §4.1) ─────────────────────────────────────────────────
HEIGHT_BASE = 150  # 키 = 150 + d50
HEIGHT_DIE = 50
BUILD_BY_D6 = {1: "slim", 2: "slim", 3: "normal", 4: "normal", 5: "sturdy", 6: "sturdy"}
BMI_BY_BUILD = {"slim": 18, "normal": 22, "sturdy": 26}
BMI_JITTER_DIE = 5  # BMI += d5 - 3
WEIGHT_CLASS = {"slim": 1, "normal": 2, "sturdy": 3}

# ─── 파생치 ──────────────────────────────────────────────────────────
HP_BASE = 40
HP_PER_CON = 6
STAMINA_BASE = 20
STAMINA_PER_CON = 2
STAMINA_REGEN_BASE = 3
STAMINA_REGEN_PER_CON = 0.3  # 턴당 회복 = 3 + CON×0.3
DEFEND_STAMINA_BONUS = 5

# ─── 판정 (설계 §5.4) ─────────────────────────────────────────────────
HIT_BASE = 60
HIT_PER_AGI_DIFF = 2
CRIT_BASE = 5
CRIT_MULT = 1.5
LUCK_ROLL_BONUS = 0.5  # (LCK - 10) × 0.5 %. 굴림에만 — 판단에는 개입 금지
LUCK_NEUTRAL = 10
STR_DAMAGE_COEF = 0.8
INT_DAMAGE_COEF = 1.0
ARMOR_SCALE = 100  # 방어 감쇄 = 100 / (100 + 방어력)
DEFEND_MULT = 0.5
FLEE_BASE = 50
FLEE_PER_AGI_DIFF = 3
HIT_MIN = 5
HIT_MAX = 95

STAMINA_COST = {"ATTACK": 5, "DEFEND": 0, "MOVE": 3, "FLEE": 4, "WAIT": 0}

# ─── 효율 스펙트럼 (설계 §4.3) ────────────────────────────────────────
MISMATCH_HIT_PENALTY = 10  # 무게등급 미달 1당 명중 -10%
MISMATCH_SPEED_PENALTY = 1
MISMATCH_STAMINA_PER_5STR = 0.5  # STR 미달 5당 스태미나 ×(1+0.5)
HEIGHT_PENALTY_PER_5CM = 5  # 장궁·장창류 키 미달 5cm 당 명중 -5%

# ─── 전투 ────────────────────────────────────────────────────────────
TURN_LIMIT = 30
HEAL_SYNERGY = 1.15  # 치유 가능 진영의 전력 보정(설계 §6.2)

# ─── 승산 · 재계획 (설계 §6.2·§6.3) ──────────────────────────────────
ODDS_MIN = 0.05
ODDS_MAX = 0.95
RETREAT_THRESHOLD_DEFAULT = 0.30
RETREAT_THRESHOLD_RANGE = (0.15, 0.45)
ODDS_COLLAPSE_STEP = 0.10  # 재진입 트리거는 0.1 씩 더 내려갈 때마다
REPLAN_MAX_CONSECUTIVE = 3
# 이탈은 자주 일어난다(성향이 그렇게 생긴 단원이 있다). 이탈마다 감독을 부르면
# 23턴에 14번을 불러 호출 예산(기획서 §7.1: 100~300)을 먹고 로그가 재계획으로 덮인다.
# 승산 붕괴·적응은 쿨다운 없이 즉시 부른다.
REPLAN_DEVIATION_COOLDOWN = 3

# ─── 순응 판정 (설계 §6.4) ────────────────────────────────────────────
PRESSURE_HP_WEIGHT = 0.5
PRESSURE_LOSS_WEIGHT = 0.3
PRESSURE_LIFE_WEIGHT = 0.2
ADJUST_RISK = -0.003
ADJUST_SACRIFICE = -0.003
ADJUST_COOPERATION = -0.002
DEVIATION_SIGMOID_GAIN = 4.0
DEVIATION_SIGMOID_SHIFT = 2.5
DEVIATION_MIN = 0.02
DEVIATION_MAX = 0.95

# ─── 지혜 마스킹 (설계 §4.6) — (하한, 상한, 단계) ────────────────────
WIS_TIERS = ((1, 7, 0), (8, 12, 1), (13, 16, 2), (17, 20, 3))
DARKNESS_TIER_PENALTY = 1

# ─── 보스 적응 (설계 §5.6) ────────────────────────────────────────────
ADAPT_WINDOW = 3  # 최근 3턴 관측
ADAPT_MAGIC_RATIO = 0.6
ADAPT_HEAL_COUNT = 2
ADAPT_DEFEND_RATIO = 0.5
ADAPT_WARD_MAGIC_RESIST = 0.30
ADAPT_WARD_TURNS = 2

# ─── 하네스 ──────────────────────────────────────────────────────────
MAX_CALLS = 300
HARNESS_RETRIES = 2

# ─── 인터미션 (설계 §7) ───────────────────────────────────────────────
GROWTH_WIN = 10
GROWTH_LOSE = 6
TRAIN_BASE = 0.5
TRAIN_PLANNING_COEF = 0.003
TRAIN_COOPERATION_COEF = 0.002
TRAIN_FATIGUE_COEF = 0.004
TRAIN_MIN = 0.10
TRAIN_MAX = 0.95
TRAIN_PARTIAL_BAND = 0.15  # 순응 확률 바로 아래 이 폭은 "부분 순응"
DILIGENT_PLANNING = 30  # planning > 30 → advantage
TIRED_FATIGUE = 60  # fatigue > 60 → disadvantage

# ─── 조언 (설계 §6.5) ─────────────────────────────────────────────────
ADVICE_MIN_MISSION = 2
ADVICE_ODDS_BELOW = 0.35
ADVICE_PROBABILITY = 0.25
