import requests, os
from datetime import datetime, timedelta

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY") or "19a26a777a8448a2bb373ad8f6abd792"
BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}

LEAGUES = {
    "1": ("PL", "الدوري الإنجليزي"),
    "2": ("PD", "الدوري الإسباني"),
    "3": ("SA", "الدوري الإيطالي"),
    "4": ("BL1", "الدوري الألماني"),
    "5": ("FL1", "الدوري الفرنسي"),
    "6": ("CL", "دوري أبطال أوروبا")
}

def safe_get(url, params=None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"❌ فشل الطلب. الكود: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ حدث خطأ أثناء الطلب: {e}")
        return None

def choose_league():
    print("\nاختر الدوري:")
    for k, (_, name) in LEAGUES.items():
        print(f"{k}. {name}")
    ch = input("اختيارك (رقم): ").strip()
    return LEAGUES.get(ch, ("PL", "الدوري الإنجليزي"))

def get_upcoming_matches(competition):
    data = safe_get(f"{BASE}/competitions/{competition}/matches", {"status": "SCHEDULED"})
    if not data or "matches" not in data:
        return []
    return data["matches"]

def get_last_matches(team_id, limit=10):
    today = datetime.utcnow().date()
    past_date = today - timedelta(days=365)
    params = {"status": "FINISHED", "dateFrom": past_date.isoformat(), "dateTo": today.isoformat()}
    data = safe_get(f"{BASE}/teams/{team_id}/matches", params=params)
    if not data or "matches" not in data:
        return []
    return data["matches"][-limit:]

def get_head_to_head(team1_id, team2_id, limit=5):
    today = datetime.utcnow().date()
    past_date = today - timedelta(days=365*2)
    params = {"status": "FINISHED", "dateFrom": past_date.isoformat(), "dateTo": today.isoformat()}
    data1 = safe_get(f"{BASE}/teams/{team1_id}/matches", params=params)
    if not data1 or "matches" not in data1:
        return []
    matches = [m for m in data1["matches"] if m["homeTeam"]["id"]==team2_id or m["awayTeam"]["id"]==team2_id]
    return matches[-limit:]

def weighted_avg(values):
    total_weight = sum(range(1, len(values)+1))
    weighted_sum = sum(v*(i+1) for i,v in enumerate(values))
    return weighted_sum / total_weight if total_weight else 0

def analyze_team(team_id, matches, home=True):
    wins = draws = losses = 0
    goals_for_list = []
    goals_against_list = []

    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None: continue
        is_home_team = (m["homeTeam"]["id"] == team_id)
        if home and not is_home_team: continue
        if not home and is_home_team: continue
        home_goals, away_goals = score["home"], score["away"]

        if is_home_team:
            goals_for_list.append(home_goals)
            goals_against_list.append(away_goals)
            if home_goals > away_goals: wins += 1
            elif home_goals == away_goals: draws += 1
            else: losses += 1
        else:
            goals_for_list.append(away_goals)
            goals_against_list.append(home_goals)
            if away_goals > home_goals: wins += 1
            elif away_goals == home_goals: draws += 1
            else: losses += 1

    total = wins + draws + losses
    return {
        "win_rate": (wins / total * 100) if total else 0,
        "attack": weighted_avg(goals_for_list),
        "defense": weighted_avg(goals_against_list)
    }

def analyze_head_to_head(team1_id, team2_id):
    matches = get_head_to_head(team1_id, team2_id)
    team1_wins = team2_wins = draws = 0
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None: continue
        if m["homeTeam"]["id"] == team1_id:
            team1_goals, team2_goals = score["home"], score["away"]
        else:
            team1_goals, team2_goals = score["away"], score["home"]

        if team1_goals > team2_goals: team1_wins += 1
        elif team1_goals < team2_goals: team2_wins += 1
        else: draws += 1

    total = team1_wins + team2_wins + draws
    if total == 0: return {"team1":0, "draw":0, "team2":0}
    return {"team1":team1_wins/total*100, "draw":draws/total*100, "team2":team2_wins/total*100}

def predict_upcoming(home_team, away_team):
    home_stats = analyze_team(home_team["id"], get_last_matches(home_team["id"], 10), home=True)
    away_stats = analyze_team(away_team["id"], get_last_matches(away_team["id"], 10), home=False)
    h_score = home_stats["win_rate"] + (home_stats["attack"] - home_stats["defense"])*5 + 5
    a_score = away_stats["win_rate"] + (away_stats["attack"] - away_stats["defense"])*5

    h2h = analyze_head_to_head(home_team["id"], away_team["id"])
    h_score += 0.2 * h2h["team1"]
    a_score += 0.2 * h2h["team2"]
    draw_score = 0.2 * h2h["draw"]

    total = h_score + a_score + draw_score
    if total == 0: total = 1
    p_home = h_score/total*100
    p_away = a_score/total*100
    p_draw = draw_score/total*100

    print(f"\n🔮 التوقع قبل المباراة:")
    print(f"🏠 فوز {home_team['name']}: {p_home:.1f}%")
    print(f"🤝 تعادل: {p_draw:.1f}%")
    print(f"🚩 فوز {away_team['name']}: {p_away:.1f}%")

    # توقع النتيجة بالأهداف
    goal_diff_factor = (p_home - p_away) / 100
    exp_home_goals = max(0, round(home_stats["attack"] - away_stats["defense"] + 1 + goal_diff_factor))
    exp_away_goals = max(0, round(away_stats["attack"] - home_stats["defense"] + 1 - goal_diff_factor))

    # تحديد النتيجة الأكثر ترجيحًا
    max_prob = max(p_home, p_draw, p_away)
    if max_prob == p_home:
        most_likely = f"فوز {home_team['name']}"
    elif max_prob == p_away:
        most_likely = f"فوز {away_team['name']}"
    else:
        if p_home > p_away:
            most_likely = f"فوز {home_team['name']}"
        elif p_away > p_home:
            most_likely = f"فوز {away_team['name']}"
        else:
            most_likely = "تعادل"

    # تعديل إذا أكثر نتيجة ترجيح هي فوز لكن توقع الأهداف يعطي تعادل
    if exp_home_goals == exp_away_goals and "فوز" in most_likely:
        most_likely = most_likely.replace("فوز", "فوز/تعادل")

    print(f"\n✅ النتيجة الأكثر ترجيحًا: {most_likely}")
    print(f"🎯 التوقع التقريبي للنتيجة: {home_team['name']} {exp_home_goals} - {exp_away_goals} {away_team['name']}")

def main():
    print("⚽ توقع نتائج المباريات القادمة (نسخة تيرمينال)\n")
    comp_code, comp_name = choose_league()
    print(f"\n📘 تم اختيار: {comp_name}\n")

    matches = get_upcoming_matches(comp_code)
    if not matches:
        print("❌ لا توجد مباريات قادمة في هذا الدوري حاليًا.")
        return

    print("📅 المباريات القادمة:")
    for i, m in enumerate(matches[:10], 1):
        h = m["homeTeam"]["name"]
        a = m["awayTeam"]["name"]
        date_str = m["utcDate"]
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_fmt = dt.strftime("%d/%m/%Y - %H:%M UTC")
        except:
            date_fmt = date_str
        print(f"{i}. {h} vs {a}  🕒 {date_fmt}")

    try:
        sel = int(input("\nاختار رقم المباراة للتوقع: "))
        if not (1 <= sel <= len(matches)): raise ValueError
    except:
        print("❌ اختيار غير صالح.")
        return

    match = matches[sel-1]
    home, away = match["homeTeam"], match["awayTeam"]
    print(f"\n🎯 التوقع لمباراة: {home['name']} 🆚 {away['name']}")
    predict_upcoming(home, away)

if __name__ == "__main__":
    main()
