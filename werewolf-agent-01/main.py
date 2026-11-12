#!/usr/bin/env python3
import json
import os
import sys
import re
import urllib.request
import urllib.error

# Disable proxies explicitly as required
proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(proxy_handler)

def http_post(url, data_dict, timeout=30, headers=None):
    if headers is None:
        headers = {}
    headers['Content-Type'] = 'application/json'
    body = json.dumps(data_dict).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    with opener.open(req, timeout=timeout) as resp:
        resp_body = resp.read().decode('utf-8')
        return json.loads(resp_body) if resp_body else {}

def post_observe(base_url):
    url = f"{base_url.rstrip('/')}/observe"
    try:
        return http_post(url, {}, timeout=30)
    except Exception:
        return None

def post_act(base_url, act_body):
    url = f"{base_url.rstrip('/')}/act"
    try:
        http_post(url, act_body, timeout=10)
    except urllib.error.HTTPError as e:
        if e.code in (400, 409):
            return
        return
    except Exception:
        return

def clean_text(s):
    if not s:
        return ""
    return re.sub(r'\s+', ' ', str(s)).strip()

def get_partner_seat(you):
    p = you.get('partner')
    if isinstance(p, dict):
        return p.get('seat')
    elif isinstance(p, int):
        return p
    return None

def get_alive_seats(view):
    players = view.get('players', [])
    alive = set()
    for p in players:
        if isinstance(p, dict) and p.get('alive'):
            alive.add(p['seat'])
    return alive

def get_seer_claimants(log, alive_seats, my_seat):
    claimants = set()
    pattern = re.compile(r"\bi(?:'| )am\s+(?:the\s+)?(?:real\s+)?seer\b|\bas\s+the\s+seer\b", re.IGNORECASE)
    for entry in log:
        if entry.get('kind') == 'speech':
            spk = entry.get('seat')
            txt = entry.get('text', '')
            if pattern.search(txt):
                claimants.add(spk)
    return claimants

def get_doctor_claimants(log, alive_seats, my_seat):
    claimants = set()
    pattern = re.compile(r"\bi(?:'| )am\s+(?:the\s+)?(?:real\s+)?doctor\b|\bas\s+the\s+doctor\b", re.IGNORECASE)
    for entry in log:
        if entry.get('kind') == 'speech':
            spk = entry.get('seat')
            txt = entry.get('text', '')
            if pattern.search(txt):
                claimants.add(spk)
    return claimants

def parse_reported_results(log):
    rep_werewolf = {}
    rep_clean = {}
    
    for entry in log:
        if entry.get('kind') == 'speech':
            spk = entry.get('seat')
            txt = entry.get('text', '')
            
            # Find werewolf reports
            wolf_matches = re.finditer(r'seat\s+(\d+)\s+(?:is\s+a?\s*)?(?:werewolf|wolf)', txt, re.IGNORECASE)
            for m in wolf_matches:
                t = int(m.group(1))
                rep_werewolf.setdefault(t, []).append(spk)
            
            wolf_chk_matches = re.finditer(r'(?:checked|inspected)\s+seat\s+(\d+)\s+.*?(?:werewolf|wolf)', txt, re.IGNORECASE)
            for m in wolf_chk_matches:
                t = int(m.group(1))
                rep_werewolf.setdefault(t, []).append(spk)
                
            # Find clean reports
            clean_matches = re.finditer(r'seat\s+(\d+)\s+(?:checked\s+)?clean', txt, re.IGNORECASE)
            for m in clean_matches:
                t = int(m.group(1))
                rep_clean.setdefault(t, []).append(spk)
                
            clean_is_matches = re.finditer(r'seat\s+(\d+)\s+is\s+(?:clean|village|villager)', txt, re.IGNORECASE)
            for m in clean_is_matches:
                t = int(m.group(1))
                rep_clean.setdefault(t, []).append(spk)
                
            clean_chk_matches = re.finditer(r'(?:checked|inspected)\s+seat\s+(\d+)\s+.*?clean', txt, re.IGNORECASE)
            for m in clean_chk_matches:
                t = int(m.group(1))
                rep_clean.setdefault(t, []).append(spk)
                
    return rep_werewolf, rep_clean

def count_accusations(log, cur_day, alive_seats):
    acc_today = {}
    acc_earlier = {}
    acc_total = {}
    
    neg_pattern = re.compile(r'\b(?:werewolf|wolf|suspicious|lying|vote|liar|sus|accused|guilty)\b', re.IGNORECASE)
    
    for entry in log:
        if entry.get('kind') == 'speech':
            spk = entry.get('seat')
            sp_day = entry.get('day', 1)
            txt = entry.get('text', '')
            
            if neg_pattern.search(txt):
                named_seats = set(int(m) for m in re.findall(r'seat\s+(\d+)', txt, re.IGNORECASE))
                for target_seat in named_seats:
                    if target_seat != spk:
                        if sp_day == cur_day:
                            acc_today[target_seat] = acc_today.get(target_seat, 0) + 1
                        else:
                            acc_earlier[target_seat] = acc_earlier.get(target_seat, 0) + 1
                        acc_total[target_seat] = acc_total.get(target_seat, 0) + 1
                        
    return acc_today, acc_earlier, acc_total

def get_votes_this_phase(log, cur_day):
    votes = []
    for entry in reversed(log):
        if entry.get('kind') == 'vote':
            votes.append(entry)
        else:
            if votes:  # end of contiguous vote entries at log end
                break
    votes.reverse()
    return votes

def get_suspicion_scores(view):
    you = view.get('you', {})
    my_seat = you.get('seat')
    cur_day = view.get('day', 1)
    alive_seats = get_alive_seats(view)
    log = view.get('log', [])
    
    seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
    rep_wolf, _ = parse_reported_results(log)
    
    votes_this_phase = get_votes_this_phase(log, cur_day)
    vote_counts = {}
    for v in votes_this_phase:
        t = v.get('target')
        if t is not None:
            vote_counts[t] = vote_counts.get(t, 0) + 1
            
    acc_today, acc_earlier, _ = count_accusations(log, cur_day, alive_seats)
    
    scores = {}
    for s in alive_seats:
        if s == my_seat:
            continue
        sc = 3 * vote_counts.get(s, 0) + 2 * acc_today.get(s, 0) + 1 * acc_earlier.get(s, 0)
        speakers = rep_wolf.get(s, [])
        if any(spk in seer_claimants for spk in speakers):
            sc += 2
        scores[s] = sc
        
    return scores, vote_counts

def make_inspect_decision(options, view):
    if not options:
        return None
        
    you = view.get('you', {})
    my_seat = you.get('seat')
    seer_results = view.get('seerResults') or []
    inspected_seats = {r['seat'] for r in seer_results if isinstance(r, dict) and 'seat' in r}
    
    alive_seats = get_alive_seats(view)
    candidates = [s for s in options if s in alive_seats and s not in inspected_seats]
    if not candidates:
        return min(options)
        
    log = view.get('log', [])
    cur_day = view.get('day', 1)
    
    seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
    rep_wolf, _ = parse_reported_results(log)
    _, _, acc_total = count_accusations(log, cur_day, alive_seats)
    
    # Priority 1: living seat reported as werewolf by another player
    p1 = [s for s in candidates if any(spk != my_seat for spk in rep_wolf.get(s, []))]
    if p1:
        return min(p1)
        
    # Priority 2: living seat who claimed to be seer (other than myself)
    p2 = [s for s in candidates if s in seer_claimants and s != my_seat]
    if p2:
        return min(p2)
        
    # Priority 3 & 4: living not-yet-inspected seat with highest accusation count
    best_seat = None
    max_acc = -1
    for s in candidates:
        cnt = acc_total.get(s, 0)
        if cnt > max_acc:
            max_acc = cnt
            best_seat = s
        elif cnt == max_acc:
            if best_seat is None or s < best_seat:
                best_seat = s
                
    return best_seat if best_seat is not None else min(candidates)

def make_protect_decision(options, view):
    if not options:
        return None
        
    you = view.get('you', {})
    my_seat = you.get('seat')
    last_protect = view.get('lastProtect')
    lp_seat = last_protect.get('seat') if isinstance(last_protect, dict) else None
    
    alive_seats = get_alive_seats(view)
    valid_opts = [s for s in options if s != my_seat and s != lp_seat and s in alive_seats]
    if not valid_opts:
        valid_opts = [s for s in options if s != my_seat and s != lp_seat]
    if not valid_opts:
        valid_opts = list(options)
        
    log = view.get('log', [])
    seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
    _, rep_clean = parse_reported_results(log)
    
    # Priority 1: living seer claimant
    p1 = [s for s in valid_opts if s in seer_claimants and s != my_seat]
    if p1:
        return min(p1)
        
    # Priority 2: living seat reported clean by seer claimant
    p2 = [s for s in valid_opts if any(spk in seer_claimants and spk != my_seat for spk in rep_clean.get(s, []))]
    if p2:
        return min(p2)
        
    # Priority 3: lowest-numbered living option
    return min(valid_opts)

def make_kill_decision(options, view):
    you = view.get('you', {})
    my_seat = you.get('seat')
    partner_seat = get_partner_seat(you)
    cur_night = view.get('day', 1)
    
    wolf_votes = view.get('wolfVotes') or []
    if partner_seat is not None:
        for entry in wolf_votes:
            if isinstance(entry, dict) and entry.get('night') == cur_night and entry.get('seat') == partner_seat:
                pt = entry.get('target')
                if pt in options and pt != my_seat and pt != partner_seat:
                    return pt
                    
    alive_seats = get_alive_seats(view)
    valid_opts = [s for s in options if s != my_seat and s != partner_seat and s in alive_seats]
    if not valid_opts:
        valid_opts = [s for s in options if s != my_seat and s != partner_seat]
    if not valid_opts:
        return None
        
    log = view.get('log', [])
    seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
    doctor_claimants = get_doctor_claimants(log, alive_seats, my_seat)
    _, rep_clean = parse_reported_results(log)
    
    # Priority 1: living seer claimant
    p1 = [s for s in valid_opts if s in seer_claimants]
    if p1:
        return min(p1)
        
    # Priority 2: living doctor claimant
    p2 = [s for s in valid_opts if s in doctor_claimants]
    if p2:
        return min(p2)
        
    # Priority 3: living seat a seer claimant reported clean
    p3 = [s for s in valid_opts if any(spk in seer_claimants and spk != my_seat for spk in rep_clean.get(s, []))]
    if p3:
        return min(p3)
        
    # Priority 4: living seat who most recently accused you or your partner
    targets_to_check = {my_seat}
    if partner_seat is not None:
        targets_to_check.add(partner_seat)
        
    for entry in reversed(log):
        if entry.get('kind') == 'speech':
            spk = entry.get('seat')
            if spk in valid_opts:
                txt = entry.get('text', '')
                named_seats = set(int(m) for m in re.findall(r'seat\s+(\d+)', txt, re.IGNORECASE))
                if named_seats.intersection(targets_to_check):
                    return spk
                    
    # Priority 5: lowest-numbered living non-werewolf option
    players = view.get('players', [])
    known_wolves = {partner_seat, my_seat} if partner_seat is not None else {my_seat}
    for p in players:
        if isinstance(p, dict) and p.get('role') == 'werewolf':
            known_wolves.add(p['seat'])
            
    non_wolf_opts = [s for s in valid_opts if s not in known_wolves]
    if non_wolf_opts:
        return min(non_wolf_opts)
        
    return min(valid_opts)

def make_vote_decision(options, view):
    you = view.get('you', {})
    my_seat = you.get('seat')
    my_role = you.get('role')
    partner_seat = get_partner_seat(you)
    cur_day = view.get('day', 1)
    
    seer_results = view.get('seerResults') or []
    alive_seats = get_alive_seats(view)
    log = view.get('log', [])
    
    # (a) If you are seer and seerResults contains a living werewolf, vote it
    if my_role == 'seer':
        living_wolves = [r['seat'] for r in seer_results if isinstance(r, dict) and r.get('werewolf') and r.get('seat') in alive_seats]
        if living_wolves:
            return min(living_wolves)
            
    seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
    rep_wolf, _ = parse_reported_results(log)
    
    votes_this_phase = get_votes_this_phase(log, cur_day)
    vote_counts = {}
    for v in votes_this_phase:
        t = v.get('target')
        if t is not None:
            vote_counts[t] = vote_counts.get(t, 0) + 1
            
    # (b) Living seer claimant (not you) reported a living seat as werewolf
    b_reports = []
    for claimant in sorted(seer_claimants):
        if claimant != my_seat:
            for target_seat, speakers in rep_wolf.items():
                if target_seat in alive_seats and claimant in speakers:
                    b_reports.append((claimant, target_seat))
                    
    if b_reports:
        claimant, reported_seat = b_reports[0]
        if my_role == 'seer':
            return claimant
        elif my_role == 'werewolf':
            if reported_seat in (my_seat, partner_seat):
                if vote_counts.get(claimant, 0) >= 1:
                    return claimant
                else:
                    scores, _ = get_suspicion_scores(view)
                    non_wolf_candidates = [s for s in alive_seats if s != my_seat and s != partner_seat]
                    if non_wolf_candidates:
                        best_s = None
                        max_sc = -1
                        for s in non_wolf_candidates:
                            sc = scores.get(s, 0)
                            if sc > max_sc:
                                max_sc = sc
                                best_s = s
                            elif sc == max_sc and (best_s is None or s < best_s):
                                best_s = s
                        return best_s if best_s is not None else min(non_wolf_candidates)
            else:
                return reported_seat
        else: # villager / doctor
            return reported_seat

    # (c) Compute suspicion per living non-self seat
    scores, vote_counts = get_suspicion_scores(view)
    candidates = [s for s in alive_seats if s != my_seat]
    
    if my_role == 'werewolf' and partner_seat in candidates:
        partner_votes = vote_counts.get(partner_seat, 0)
        strictly_leads = partner_votes >= 3 and all(partner_votes > vote_counts.get(other, 0) for other in alive_seats if other != partner_seat)
        if not strictly_leads:
            candidates.remove(partner_seat)
            
    if not candidates:
        return None
        
    max_score = max(scores.get(s, 0) for s in candidates)
    if max_score == 0 and cur_day == 1:
        return None
        
    best_seats = [s for s in candidates if scores.get(s, 0) == max_score]
    return min(best_seats)

def build_view_summary(view):
    you = view.get('you', {})
    my_seat = you.get('seat')
    my_role = you.get('role')
    cur_day = view.get('day', 1)
    log = view.get('log', [])
    players = view.get('players', [])
    
    alive_seats = get_alive_seats(view)
    alive_str = ", ".join(str(s) for s in sorted(alive_seats))
    
    rev_roles = {}
    for p in players:
        if isinstance(p, dict) and p.get('role'):
            rev_roles[p['seat']] = p['role']
    for entry in log:
        k = entry.get('kind')
        if k == 'exile' and entry.get('seat') is not None:
            rev_roles[entry['seat']] = entry.get('role', 'unknown')
        elif k == 'dawn':
            died = entry.get('died')
            r = entry.get('role', 'unknown')
            if isinstance(died, int):
                rev_roles[died] = r
            elif isinstance(died, list):
                for ds in died:
                    rev_roles[ds] = r
                    
    rev_roles_str = ", ".join(f"Seat {s}: {r}" for s, r in sorted(rev_roles.items())) if rev_roles else "None"
    
    deaths = []
    for entry in log:
        k = entry.get('kind')
        if k == 'exile':
            s = entry.get('seat')
            r = entry.get('role', 'unknown')
            if s is not None:
                deaths.append(f"Seat {s} exiled ({r})")
        elif k == 'dawn':
            died = entry.get('died')
            r = entry.get('role', 'unknown')
            if isinstance(died, int):
                deaths.append(f"Seat {died} died at dawn ({r})")
            elif isinstance(died, list):
                for ds in died:
                    deaths.append(f"Seat {ds} died at dawn ({r})")
    deaths_str = "; ".join(deaths) if deaths else "None"
    
    seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
    seer_claims_str = ", ".join(f"Seat {s}" for s in sorted(seer_claimants)) if seer_claimants else "None"
    rep_wolf, rep_clean = parse_reported_results(log)
    
    rep_list = []
    for s, speakers in rep_wolf.items():
        rep_list.append(f"Seat {s} reported werewolf by {speakers}")
    for s, speakers in rep_clean.items():
        rep_list.append(f"Seat {s} reported clean by {speakers}")
    rep_str = "; ".join(rep_list) if rep_list else "None"
    
    todays_speeches = []
    for entry in log:
        if entry.get('kind') == 'speech' and entry.get('day') == cur_day:
            spk = entry.get('seat')
            txt = entry.get('text', '')
            todays_speeches.append(f"Seat {spk}: \"{txt}\"")
    speeches_str = " | ".join(todays_speeches) if todays_speeches else "None"
    
    todays_votes = []
    for entry in log:
        if entry.get('kind') == 'vote' and entry.get('day') == cur_day:
            voter = entry.get('seat')
            target = entry.get('target')
            todays_votes.append(f"Seat {voter} voted seat {target}")
    votes_str = ", ".join(todays_votes) if todays_votes else "None"
    
    intent = "stay quiet and observe while expressing village alignment"
    partner_seat = get_partner_seat(you)
    for c in sorted(seer_claimants):
        if c != my_seat:
            for w_seat, speakers in rep_wolf.items():
                if w_seat in alive_seats and c in speakers:
                    if w_seat == my_seat or (partner_seat is not None and w_seat == partner_seat):
                        continue
                    intent = f"support the seer claim and accuse seat {w_seat}"
                    break
            if "support" in intent:
                break
                
    if "support" not in intent:
        acc_today, _, _ = count_accusations(log, cur_day, alive_seats)
        if acc_today.get(my_seat, 0) > 0:
            intent = "defend yourself against accusations"
        elif my_role == 'werewolf':
            scores, _ = get_suspicion_scores(view)
            candidates = [s for s in alive_seats if s != my_seat and (partner_seat is None or s != partner_seat)]
            if candidates:
                max_score = max(scores.get(s, 0) for s in candidates)
                best_seats = [s for s in candidates if scores.get(s, 0) == max_score]
                best_s = min(best_seats) if best_seats else None
                if best_s is not None:
                    intent = f"accuse seat {best_s}"
                else:
                    intent = "stay quiet and observe while expressing village alignment"
            else:
                intent = "stay quiet and observe while expressing village alignment"
        else:
            acc_candidates = [(cnt, s) for s, cnt in acc_today.items() if s != my_seat and (partner_seat is None or s != partner_seat) and cnt > 0]
            if acc_candidates:
                acc_candidates.sort(key=lambda x: (-x[0], x[1]))
                intent = f"accuse seat {acc_candidates[0][1]}"
                
    summary = (
        f"My seat: {my_seat}. My role: {my_role}.\n"
        f"Day: {cur_day}.\n"
        f"Alive seats: {alive_str}.\n"
        f"Revealed roles: {rev_roles_str}.\n"
        f"Deaths so far: {deaths_str}.\n"
        f"Seer claims: {seer_claims_str}.\n"
        f"Reported results: {rep_str}.\n"
        f"Today's speeches so far: {speeches_str}.\n"
        f"Votes so far today: {votes_str}.\n"
        f"Instruction: {intent}."
    )
    return summary

def generate_model_statement(summary, max_chars):
    base_url = os.environ.get('OPENAI_BASE_URL')
    api_key = os.environ.get('OPENAI_API_KEY')
    if not base_url or not api_key:
        return None
        
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    payload = {
        'model': 'gemini-4-argon',
        'max_tokens': 300,
        'temperature': 0,
        'messages': [
            {
                'role': 'system',
                'content': 'You are one player in a game of Werewolf, speaking in the public debate. Reply with only your statement: first person, plain words, one line, at most 480 characters, no quotes, no JSON. Never reveal or hint at being a werewolf; if you are a werewolf, speak as an ordinary villager. Never claim to be the seer or the doctor unless the instruction explicitly tells you to make that claim.'
            },
            {
                'role': 'user',
                'content': summary
            }
        ]
    }
    
    try:
        res = http_post(url, payload, timeout=40, headers=headers)
        choices = res.get('choices', [])
        if choices and isinstance(choices, list):
            content = choices[0].get('message', {}).get('content', '')
            cleaned = clean_text(content)
            if cleaned and len(cleaned) <= max_chars:
                return cleaned
    except Exception:
        pass
        
    return None

def make_speak_decision(game_id, max_chars, view):
    you = view.get('you', {})
    my_role = you.get('role')
    my_seat = you.get('seat')
    cur_day = view.get('day', 1)
    log = view.get('log', [])
    seer_results = view.get('seerResults') or []
    alive_seats = get_alive_seats(view)
    
    my_speeches = [sp.get('text', '').lower() for sp in log if sp.get('kind') == 'speech' and sp.get('seat') == my_seat]
    
    # 1 & 2: Scripted seer statements (stay scripted)
    if my_role == 'seer':
        unannounced_wolf = []
        unannounced_clean = []
        for r in seer_results:
            if isinstance(r, dict):
                seat = r.get('seat')
                night = r.get('night', 1)
                is_wolf = r.get('werewolf')
                announced = any(f"seat {seat}" in sp and ("werewolf" in sp or "wolf" in sp or "clean" in sp) for sp in my_speeches)
                if not announced:
                    if is_wolf and seat in alive_seats:
                        unannounced_wolf.append((seat, night))
                    elif not is_wolf:
                        unannounced_clean.append((seat, night))
                        
        if unannounced_wolf:
            w_seat, w_night = unannounced_wolf[0]
            stmt = f"I am the seer. I checked seat {w_seat} on night {w_night} and seat {w_seat} is a werewolf. Vote seat {w_seat} today."
            if unannounced_clean:
                clean_seats_str = " and ".join(f"seat {s}" for s, _ in unannounced_clean)
                add_str = f" {clean_seats_str.capitalize()} checked clean."
                if len(stmt) + len(add_str) <= max_chars:
                    stmt += add_str
            return clean_text(stmt)[:max_chars]

        other_seer_claimants = [s for s in get_seer_claimants(log, alive_seats, my_seat) if s != my_seat]
        if other_seer_claimants:
            c_seat = min(other_seer_claimants)
            checks_list = []
            for r in seer_results:
                if isinstance(r, dict):
                    s = r.get('seat')
                    n = r.get('night', 1)
                    res = "werewolf" if r.get('werewolf') else "clean"
                    checks_list.append(f"night {n} seat {s} {res}")
            checks_str = ", ".join(checks_list)
            stmt = f"Seat {c_seat} is lying. I am the real seer. My checks: {checks_str}. Vote seat {c_seat}."
            return clean_text(stmt)[:max_chars]

    # Model gateway attempt before template fallback
    try:
        summary = build_view_summary(view)
        model_stmt = generate_model_statement(summary, max_chars)
        if model_stmt:
            return model_stmt
    except Exception:
        pass

    # 3: Template fallbacks
    if my_role in ('villager', 'doctor', 'seer'):
        rep_wolf, _ = parse_reported_results(log)
        seer_claimants = get_seer_claimants(log, alive_seats, my_seat)
        for c in sorted(seer_claimants):
            if c != my_seat:
                for w_seat, speakers in rep_wolf.items():
                    if w_seat in alive_seats and c in speakers:
                        stmt = f"I trust seat {c}'s claim. Seat {w_seat} is the vote today."
                        return clean_text(stmt)[:max_chars]
                        
        _, _, acc_total = count_accusations(log, cur_day, alive_seats)
        acc_candidates = [(cnt, -s, s) for s, cnt in acc_total.items() if s != my_seat and s in alive_seats and cnt > 0]
        if acc_candidates:
            acc_candidates.sort(reverse=True)
            target_s = acc_candidates[0][2]
            stmt = f"Seat {target_s} has been accused by several players and has said little. I want answers from seat {target_s}."
            return clean_text(stmt)[:max_chars]
            
        stmt = "No deaths yet tell us little. Watch who pushes votes without reasons."
        return clean_text(stmt)[:max_chars]

    elif my_role == 'werewolf':
        partner_seat = get_partner_seat(you)
        scores, _ = get_suspicion_scores(view)
        candidates = [(sc, -s, s) for s, sc in scores.items() if s != my_seat and s != partner_seat and s in alive_seats]
        if candidates:
            candidates.sort(reverse=True)
            target_s = candidates[0][2]
            stmt = f"I am village. Seat {target_s}'s story keeps changing; that is where my vote is going."
            return clean_text(stmt)[:max_chars]
        else:
            stmt = "I am village. Watch who pushes votes without reasons."
            return clean_text(stmt)[:max_chars]

    return None

def handle_decision(game_id, decision_kind, options, max_chars, view):
    try:
        if decision_kind == 'speak':
            stmt = make_speak_decision(game_id, max_chars, view)
            if stmt:
                return {"game": game_id, "decision": "speak", "text": stmt}
            else:
                return {"game": game_id, "decision": "speak", "pass": True}
        elif decision_kind == 'vote':
            target = make_vote_decision(options, view)
            return {"game": game_id, "decision": "vote", "target": target}
        elif decision_kind in ('inspect', 'protect', 'kill'):
            if decision_kind == 'inspect':
                target = make_inspect_decision(options, view)
            elif decision_kind == 'protect':
                target = make_protect_decision(options, view)
            elif decision_kind == 'kill':
                target = make_kill_decision(options, view)
            else:
                target = None
            return {"game": game_id, "decision": decision_kind, "target": target}
    except Exception:
        pass
        
    if decision_kind == 'speak':
        return {"game": game_id, "decision": "speak", "pass": True}
    else:
        return {"game": game_id, "decision": decision_kind, "target": None}

def main():
    base_url = os.environ.get('MAKEFUN_ENV_URL', 'http://localhost:8000')
    while True:
        res = post_observe(base_url)
        if not res:
            continue
        if res.get('done'):
            break
            
        pending = res.get('pending', [])
        def get_game_id(item):
            g = item.get('game', 0)
            try:
                return int(g)
            except Exception:
                return 0
                
        pending.sort(key=get_game_id)
        
        for item in pending:
            game_id = item.get('game')
            decision_kind = item.get('decision')
            options = item.get('options', [])
            max_chars = item.get('max_chars', 480)
            view = item.get('view', {})
            
            act_payload = handle_decision(game_id, decision_kind, options, max_chars, view)
            if act_payload:
                post_act(base_url, act_payload)

if __name__ == '__main__':
    main()
