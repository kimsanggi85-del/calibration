#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 검교정 임박 알람메일 자동발송 (단일 파일 통합본)
 TAEJIN DITECH · Measuring Instrument Calibration Alert
================================================================================
 매일 아침 계측기 데이터를 점검해 '차기검교정일자'가 30일 이내이거나 기한이 지난
 계측기를 골라 HTML 표 형태의 알림 메일을 자동 발송합니다.
 데이터(105대)와 설명서를 이 파일 하나에 모두 담았습니다.

--------------------------------------------------------------------------------
[설치 1] Gmail 앱 비밀번호
  Google 계정 > 보안 > 2단계 인증 켜기 > 앱 비밀번호 > 16자리 생성·복사

[설치 2] 이 파일(notify.py)을 GitHub 리포에 올리고 Secrets 3개 등록
  (Settings > Secrets and variables > Actions > New repository secret)
    SMTP_USER = 보내는 Gmail 주소
    SMTP_PASS = 16자리 앱 비밀번호 (공백 없이)
    MAIL_TO   = 받는 사람 (여러 명은 쉼표로:  a@x.com, b@y.com)

[설치 3] 워크플로 파일 1개만 별도 생성 (GitHub 규칙상 위치 고정)
  경로:  .github/workflows/calib-alert.yml
  아래 내용을 그대로 붙여넣기:
  ------------------------------------------------------------------
  name: 검교정 임박 알림
  on:
    schedule:
      - cron: "0 23 * * *"      # 매일 08:00 KST
    workflow_dispatch:
  jobs:
    notify:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: "3.12" }
        - env:
            SMTP_USER: ${{ secrets.SMTP_USER }}
            SMTP_PASS: ${{ secrets.SMTP_PASS }}
            MAIL_TO:   ${{ secrets.MAIL_TO }}
          run: python notify.py
  ------------------------------------------------------------------
  Actions 탭 > Run workflow 로 즉시 발송 테스트. 이후 매일 자동 실행.

[데이터 최신화]  두 가지 방법 중 택1
  (A) 같은 폴더에 data.json 을 두면 그 파일을 우선 사용합니다.
      → 관리대장 HTML의 [데이터 백업(JSON)] 으로 받아 data.json 으로 커밋.
  (B) data.json 이 없으면 이 파일 아래 INSTRUMENTS 데이터를 사용합니다.
      (직접 수정 시 맨 아래 INSTRUMENTS 딕셔너리 편집)

[옵션] 환경변수로 조정
  ALERT_DAYS(기본30) / SMTP_PORT(465 SSL, 587 STARTTLS) / SEND_WHEN_EMPTY=1
  발송 빈도 줄이려면 워크플로 cron 을 주1회(0 23 * * 0)로.

[로컬 테스트] (메일 실제 발송)
  set SMTP_USER / SMTP_PASS / MAIL_TO 환경변수 후  python notify.py
================================================================================
"""
import os, json, smtplib, ssl, sys
from datetime import date, datetime
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

ALERT_DAYS = int(os.getenv("ALERT_DAYS", "30"))


def load_data():
    """data.json 이 옆에 있으면 우선 사용, 없으면 내장 INSTRUMENTS 사용."""
    here = os.path.dirname(os.path.abspath(__file__))
    ext = os.path.join(here, "data.json")
    if os.path.exists(ext):
        with open(ext, encoding="utf-8") as f:
            return json.load(f)
    return INSTRUMENTS


def parse_d(s):
    if not s:
        return None
    s = str(s).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def collect():
    db = load_data()
    today = date.today()
    rows = []
    for team, items in db.items():
        for r in items:
            if r.get("disposal"):           # 폐기 제외
                continue
            nd = parse_d(r.get("next"))
            if nd is None:                  # 차기일자 미입력 제외
                continue
            d = (nd - today).days
            if d <= ALERT_DAYS:             # 만료(음수) + 임박(<=기준일) 포함
                rows.append({**r, "team": team, "next_d": nd, "days": d})
    rows.sort(key=lambda x: x["days"])       # 급한 순
    return rows, today


def status(d):
    if d < 0:
        return ("만료", "#b3261e", "#fdecea", "D+%d" % (-d))
    if d == 0:
        return ("당일", "#b3261e", "#fdecea", "D-DAY")
    if d <= 30:
        return ("30일 이내", "#d4380d", "#fff1ec", "D-%d" % d)
    if d <= 60:
        return ("31~60일", "#d48806", "#fff8e6", "D-%d" % d)
    return ("정상", "#2e7d46", "#eaf6ee", "D-%d" % d)


def build_html(rows, today):
    exp = sum(1 for r in rows if r["days"] < 0)
    soon = sum(1 for r in rows if 0 <= r["days"] <= ALERT_DAYS)
    td = "padding:8px 10px;border-bottom:1px solid #eef2f6;font-size:12px"
    trs = []
    for r in rows:
        lab, col, bg, dd = status(r["days"])
        trs.append(
            '<tr>'
            '<td style="%s;color:#5a6678;text-align:center">%s</td>'
            '<td style="%s;font-size:13px;font-weight:700;color:#1b2330">%s'
            '<div style="font-weight:400;color:#8a94a6;font-size:11px">%s</div></td>'
            '<td style="%s;font-family:monospace;color:#1b2330">%s</td>'
            '<td style="%s;color:#1b2330">%s</td>'
            '<td style="%s;color:#5a6678">%s</td>'
            '<td style="%s;font-family:monospace;font-weight:700;text-align:center">%s</td>'
            '<td style="%s;text-align:center">'
            '<span style="display:inline-block;font-family:monospace;font-size:11px;'
            'font-weight:700;color:%s;background:%s;padding:3px 9px;border-radius:20px">'
            '%s &middot; %s</span></td></tr>'
            % (td, r["team"], td, r.get("name", ""), r.get("spec", ""),
               td, r.get("serial", ""), td, r.get("owner", ""),
               td, r.get("loc", ""), td, r["next_d"].strftime("%Y.%m.%d"),
               td, col, bg, dd, lab))

    thh = 'padding:9px 10px;font-size:11px;color:#5a6678;border-bottom:1px solid #e2e7ee'
    head = (
        '<th style="%s;text-align:center">팀</th>'
        '<th style="%s;text-align:left">품명 / 규격</th>'
        '<th style="%s;text-align:left">기기번호</th>'
        '<th style="%s;text-align:left">담당자</th>'
        '<th style="%s;text-align:left">위치</th>'
        '<th style="%s;text-align:center">차기검교정일</th>'
        '<th style="%s;text-align:center">잔여 / 상태</th>'
        % (thh, thh, thh, thh, thh, thh, thh))

    return (
        '<!DOCTYPE html><html><body style="margin:0;background:#eef1f4;'
        'font-family:\'Malgun Gothic\',sans-serif">'
        '<div style="max-width:760px;margin:0 auto;padding:24px">'
        '<div style="background:#1b2330;color:#fff;padding:18px 22px;border-radius:12px 12px 0 0">'
        '<div style="font-size:11px;letter-spacing:1px;color:#9aa6bb;font-family:monospace">'
        'TAEJIN DITECH &middot; CALIBRATION ALERT</div>'
        '<div style="font-size:19px;font-weight:800;margin-top:4px">검교정 임박 알림 (%d일 이내)</div>'
        '<div style="font-size:12px;color:#c3ccd9;margin-top:6px">기준일 %s &middot; '
        '만료 <b style="color:#ff8a7a">%d</b>건 &middot; 임박 <b style="color:#ffc46b">%d</b>건</div></div>'
        '<div style="background:#fff;border:1px solid #e2e7ee;border-top:0;'
        'border-radius:0 0 12px 12px;overflow:hidden">'
        '<table style="border-collapse:collapse;width:100%%"><thead>'
        '<tr style="background:#f7f9fb">%s</tr></thead><tbody>%s</tbody></table></div>'
        '<div style="font-size:11px;color:#8a94a6;margin-top:12px;font-family:monospace">'
        '본 메일은 검교정 관리대장에서 매일 자동 발송됩니다.</div></div></body></html>'
        % (ALERT_DAYS, today.strftime("%Y.%m.%d"), exp, soon, head, "".join(trs)))


def main():
    rows, today = collect()
    send_empty = os.getenv("SEND_WHEN_EMPTY", "0") == "1"
    if not rows and not send_empty:
        print("임박/만료 대상 없음 — 메일 미발송")
        return

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    mfrom = os.getenv("MAIL_FROM", user)
    tos = [a.strip() for a in os.environ["MAIL_TO"].split(",") if a.strip()]

    if rows:
        exp = sum(1 for r in rows if r["days"] < 0)
        soon = len(rows) - exp
        subj = "[검교정 알림] 임박 %d건 / 만료 %d건 (%s)" % (soon, exp, today.strftime("%m.%d"))
        html = build_html(rows, today)
    else:
        subj = "[검교정 알림] 임박/만료 계측기 없음 (%s)" % today.strftime("%m.%d")
        html = ("<p style='font-family:sans-serif'>%s 기준 %d일 이내 검교정 대상이 없습니다.</p>"
                % (today.strftime("%Y.%m.%d"), ALERT_DAYS))

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subj, "utf-8")
    msg["From"] = formataddr((str(Header("검교정 관리대장", "utf-8")), mfrom))
    msg["To"] = ", ".join(tos)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            s.login(user, pw)
            s.sendmail(mfrom, tos, msg.as_string())
    else:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.sendmail(mfrom, tos, msg.as_string())
    print("발송 완료 → %s (대상 %d건)" % (tos, len(rows)))


# ============================================================================
#  계측기 데이터 (data.json 이 옆에 있으면 그쪽을 우선 사용)
# ============================================================================
INSTRUMENTS = {
    "생산": [
        {
            "no": "1",
            "name": "내외측 캘리퍼(디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "14058732",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "47",
            "owner": "",
            "remark": "생산 심팩300톤(47)"
        },
        {
            "no": "2",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A17051617",
            "buy": "2018-12-24",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "29",
            "owner": "",
            "remark": "생산 유성환"
        },
        {
            "no": "3",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "15198080",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "32",
            "owner": "",
            "remark": "생산 윤애순"
        },
        {
            "no": "4",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A15092695",
            "buy": "2018-02-01",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "B동  3호기 고성신"
        },
        {
            "no": "5",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "15138133",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "35",
            "owner": "",
            "remark": "생산 정주은"
        },
        {
            "no": "6",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A19257001",
            "buy": "2020-02-05",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "6",
            "owner": "",
            "remark": "생산 김태주"
        },
        {
            "no": "7",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "HE20669",
            "buy": "2025-11-04",
            "disposal": "",
            "calib": "",
            "next": "",
            "loc": "6",
            "owner": "",
            "remark": "생산 김태주"
        },
        {
            "no": "8",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A19193907",
            "buy": "2021-01-07",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "46",
            "owner": "",
            "remark": "심팩 300톤 46호기"
        },
        {
            "no": "9",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A19193917",
            "buy": "2021-01-07",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "45",
            "owner": "",
            "remark": "심팩 300톤 45호기"
        },
        {
            "no": "10",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "GJO8582",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "48",
            "owner": "",
            "remark": "생산 48호기"
        },
        {
            "no": "11",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A18169813",
            "buy": "2020-08-10",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "4",
            "owner": "",
            "remark": "생산 정승옥"
        },
        {
            "no": "12",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A19125220",
            "buy": "2021-06-22",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "37",
            "owner": "",
            "remark": "생산 왕석주"
        },
        {
            "no": "13",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "B18190675",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "생산 한영숙"
        },
        {
            "no": "14",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~150)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "B21314667",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "1",
            "owner": "",
            "remark": "생산 하경자"
        },
        {
            "no": "15",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~300)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "0025003",
            "buy": "2022-06-03",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "생산 강창구부장님"
        },
        {
            "no": "16",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "GJ08901",
            "buy": "2024-07-10",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "41",
            "owner": "",
            "remark": "생산 임혜종"
        },
        {
            "no": "17",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "GJ08920",
            "buy": "2024-07-10",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "36",
            "owner": "",
            "remark": "생산 36호기"
        },
        {
            "no": "18",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "GJ08587",
            "buy": "2024-07-10",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "49",
            "owner": "",
            "remark": "생산 49호기"
        },
        {
            "no": "19",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~150)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "13035828",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "49",
            "owner": "",
            "remark": "생산 강창구"
        },
        {
            "no": "20",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19192728",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "37",
            "owner": "",
            "remark": "생산 39호기"
        },
        {
            "no": "21",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "18017860",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "6",
            "owner": "",
            "remark": "생산 40호기"
        },
        {
            "no": "22",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "13044029",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "생산 32호기"
        },
        {
            "no": "23",
            "name": "디지털 게이지",
            "spec": "0~25.6mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "23084201",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "35",
            "owner": "",
            "remark": "생산 34호기"
        },
        {
            "no": "24",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "035610",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "34",
            "owner": "",
            "remark": "B동  28호기"
        },
        {
            "no": "25",
            "name": "디지털 게이지",
            "spec": "0~50.8mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "13106",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "1",
            "owner": "",
            "remark": "B동 32호기 정주은"
        },
        {
            "no": "26",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "17234365",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "37",
            "owner": "",
            "remark": "B동 32호기 정주은"
        },
        {
            "no": "27",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "13085269",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "37",
            "owner": "",
            "remark": "B동 32호기 정주은"
        },
        {
            "no": "28",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19025868",
            "buy": "2021-01-07",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "B동 32호기 정주은"
        },
        {
            "no": "29",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19007455",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "38",
            "owner": "",
            "remark": "B동 32호기 정주은"
        },
        {
            "no": "30",
            "name": "게이지압용 압력계 (다이얼형)",
            "spec": "(0~1)Mpa",
            "maker": "",
            "serial": "NONE",
            "buy": "2022-10-25",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "B동 32호기 정주은"
        },
        {
            "no": "31",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "GJ08906",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "43",
            "owner": "",
            "remark": "생산 세동 43호기"
        },
        {
            "no": "32",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "23103131",
            "buy": "2024-07-15",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": "생산 41호기"
        },
        {
            "no": "33",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19183308",
            "buy": "2024-10-11",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "40",
            "owner": "",
            "remark": "생산 내외경지그2호기"
        },
        {
            "no": "34",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19164479",
            "buy": "2024-10-11",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "40",
            "owner": "",
            "remark": "생산 내외경지그2호기"
        },
        {
            "no": "35",
            "name": "외측 마이크로미터 (디지털튜브형)",
            "spec": "0~25mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "85111152",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "37",
            "owner": "",
            "remark": ""
        },
        {
            "no": "36",
            "name": "다이얼 게이지",
            "spec": "0~10mm(0.01)mm",
            "maker": "MITUTOYO",
            "serial": "JAG235",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "41",
            "owner": "",
            "remark": ""
        },
        {
            "no": "37",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "GJ08912",
            "buy": "2024-07-10",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2",
            "owner": "",
            "remark": "생산 2호기"
        },
        {
            "no": "38",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19192660",
            "buy": "2024-08-20",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "",
            "owner": "",
            "remark": ""
        },
        {
            "no": "39",
            "name": "외측마이크로미터 (디지털포인터형)",
            "spec": "0~25mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "63057680",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "28",
            "owner": "",
            "remark": ""
        }
    ],
    "품질": [
        {
            "no": "1",
            "name": "전기식 지시저울",
            "spec": "25kg/5g",
            "maker": "CAS",
            "serial": "E18062901",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF ATC 이유선"
        },
        {
            "no": "2",
            "name": "전기식 지시저울",
            "spec": "30kg/5g",
            "maker": "에이컴",
            "serial": "ACD60071",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF ATC 진정화"
        },
        {
            "no": "3",
            "name": "전기식 지시저울",
            "spec": "30kg/5g",
            "maker": "A&D전자저울",
            "serial": "H19-22397",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF ATC 송경옥"
        },
        {
            "no": "4",
            "name": "전기식 지시저울",
            "spec": "30kg/5g",
            "maker": "A&D전자저울",
            "serial": "H20-00030",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF ATC 김미선"
        },
        {
            "no": "5",
            "name": "전기식 지시저울",
            "spec": "25kg/5g",
            "maker": "CAS",
            "serial": "CQE66",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF 씰 전귀옥"
        },
        {
            "no": "6",
            "name": "전기식 지시저울",
            "spec": "30kg/5g",
            "maker": "A&D전자저울",
            "serial": "H20-00027",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF씰 서성자"
        },
        {
            "no": "7",
            "name": "전기식 지시저울",
            "spec": "30kg/5g",
            "maker": "A&D전자저울",
            "serial": "H20-15361",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "2층검사실",
            "owner": "오윤정",
            "remark": "품질 SKF씰 차찬이"
        },
        {
            "no": "8",
            "name": "전기식 지시저울",
            "spec": "2000g/0.1g",
            "maker": "CAS",
            "serial": "BM625",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "9",
            "name": "전기식 지시저울",
            "spec": "30kg/5g",
            "maker": "A&D전자저울",
            "serial": "H19-00051",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 2층 ATC 강란희"
        },
        {
            "no": "10",
            "name": "삼차원 좌표 측정기",
            "spec": "CNC 자동(600)",
            "maker": "ABERLINK",
            "serial": "14135",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "11",
            "name": "삼차원 좌표 측정기",
            "spec": "수동",
            "maker": "ABERLINK",
            "serial": "14923",
            "buy": "2017-09-25",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "12",
            "name": "측정투영기",
            "spec": "V-16E",
            "maker": "NIKON",
            "serial": "14015",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "13",
            "name": "로크웰 경도시험기",
            "spec": "60kgf~150kgf",
            "maker": "DAEKYUNG TECH",
            "serial": "11-K1574",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "14",
            "name": "형상측정기",
            "spec": "0 ~100mm (C_3200)",
            "maker": "MITUTOYO",
            "serial": "300582409",
            "buy": "2024-11-29",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "15",
            "name": "형상측정기",
            "spec": "0 ~100mm (C_3200)",
            "maker": "MITUTOYO",
            "serial": "300572409",
            "buy": "2024-11-29",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "16",
            "name": "고강도 비커스경도기",
            "spec": "HV-112",
            "maker": "MITUTOYO",
            "serial": "B00021402",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "17",
            "name": "조도측정기",
            "spec": "SJ-410",
            "maker": "MITUTOYO",
            "serial": "000481704",
            "buy": "2017-07-18",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "18",
            "name": "비접촉",
            "spec": "",
            "maker": "MITUTOYO",
            "serial": "73966235",
            "buy": "2025-01-02",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "19",
            "name": "정밀정반",
            "spec": "2000*1000",
            "maker": "금성정밀계측기",
            "serial": "73966235",
            "buy": "2025-01-02",
            "disposal": "",
            "calib": "2025-07-16",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 측정실"
        },
        {
            "no": "20",
            "name": "외측마이크로미터 (아날로그)",
            "spec": "0~25mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "09710",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "허미정",
            "remark": "품질 허미정"
        },
        {
            "no": "21",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A19257010",
            "buy": "2020-02-05",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "김상기",
            "remark": "품질 김상기"
        },
        {
            "no": "22",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A23168711",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "허미정",
            "remark": "품질 허미정"
        },
        {
            "no": "23",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~300)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "0025046",
            "buy": "2022-06-03",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "허미정",
            "remark": "품질 허미정"
        },
        {
            "no": "24",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "B23037007",
            "buy": "2023-06-12",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "문수진",
            "remark": "품질 문수진"
        },
        {
            "no": "25",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "B23036977",
            "buy": "2023-06-12",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 문수진"
        },
        {
            "no": "26",
            "name": "외측마이크로미터 (디지털포인터형)",
            "spec": "0~25mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "72037018",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 문수진"
        },
        {
            "no": "27",
            "name": "높이 게이지 (디지털형)",
            "spec": "0~300mm(0.01mm)",
            "maker": "MITUTOYO",
            "serial": "0308446",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 문수진"
        },
        {
            "no": "28",
            "name": "다이얼 게이지",
            "spec": "0.5mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "CMNH69",
            "buy": "2024-07-10",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 문수진"
        },
        {
            "no": "29",
            "name": "인디게이터 (디지털형)",
            "spec": "12.7mm/0.001mm",
            "maker": "MITUTOYO",
            "serial": "18019184",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질 문수진"
        },
        {
            "no": "30",
            "name": "인디게이터 (디지털형)",
            "spec": "25.4mm/0.001mm",
            "maker": "MITUTOYO",
            "serial": "18171804",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질팀 정반위 제일 많이 씀"
        },
        {
            "no": "31",
            "name": "광조도계",
            "spec": "1332A",
            "maker": "TES",
            "serial": "140710687",
            "buy": "",
            "disposal": "",
            "calib": "2025-11-19",
            "next": "2026-11-19",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "품질"
        },
        {
            "no": "32",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19025860",
            "buy": "2021-01-07",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "여분"
        },
        {
            "no": "33",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "19192676",
            "buy": "2024-08-20",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "여분"
        },
        {
            "no": "34",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "HE20517",
            "buy": "2025-11-04",
            "disposal": "",
            "calib": "",
            "next": "",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "여분"
        },
        {
            "no": "35",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "Dasqua",
            "serial": "HE20477",
            "buy": "2025-11-04",
            "disposal": "",
            "calib": "",
            "next": "",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "여분"
        },
        {
            "no": "36",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "B23036986",
            "buy": "2021-01-07",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "여분"
        },
        {
            "no": "-",
            "name": "전기식 지시저울",
            "spec": "252g/0.1mg",
            "maker": "A&D전자저울",
            "serial": "16009311",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "측정실",
            "owner": "오현민",
            "remark": "계단 밑 창고"
        }
    ],
    "설계&개발": [
        {
            "no": "1",
            "name": "내외측캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A15106023",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "1층 사무실",
            "owner": "채은지",
            "remark": ""
        },
        {
            "no": "2",
            "name": "내외측캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "18074916",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "1층 사무실",
            "owner": "이재성",
            "remark": ""
        },
        {
            "no": "3",
            "name": "내외측캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "13033743",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실앞정반",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "4",
            "name": "내외측캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "13458686",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발가공실",
            "owner": "이상철",
            "remark": ""
        },
        {
            "no": "5",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "B23036976",
            "buy": "2023-06-12",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "6",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~200)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "A23183350",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "7",
            "name": "내외측 캘리퍼 (아날로그)",
            "spec": "(0~300)mm/0.05mm",
            "maker": "MITUTOYO",
            "serial": "2197255",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실앞정반",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "8",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~300)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "0025045",
            "buy": "2022-06-03",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "1층사무실",
            "owner": "채은지",
            "remark": ""
        },
        {
            "no": "9",
            "name": "외측마이크로미터 (디지털형)",
            "spec": "0~25mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "20457134",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "10",
            "name": "외측마이크로미터 (디지털형)",
            "spec": "0~25mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "55167160",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실안",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "11",
            "name": "외측마이크로미터 (포인터형)",
            "spec": "0~25mm(0.01mm)",
            "maker": "MITUTOYO",
            "serial": "71537237",
            "buy": "2022-10-31",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실앞정반",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "12",
            "name": "외측마이크로미터 (아날로그)",
            "spec": "0~25mm(0.01mm)",
            "maker": "N S K",
            "serial": "HI2649",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "13",
            "name": "외측마이크로미터 (포인터형)(아날로그)",
            "spec": "0~25mm(0.01mm)",
            "maker": "MITUTOYO",
            "serial": "36077966",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "14",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "13033743",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실앞정반",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "15",
            "name": "테스트 인디케이터",
            "spec": "1㎛",
            "maker": "MITUTOYO",
            "serial": "MNM483",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "16",
            "name": "테스트 인디케이터",
            "spec": "(0~0.8)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "AUEX08",
            "buy": "2022-10-25",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "17",
            "name": "테스트 인디케이터",
            "spec": "(0~100)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "RZU474",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실앞정반",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "18",
            "name": "테스트 인디케이터",
            "spec": "1㎛",
            "maker": "MITUTOYO",
            "serial": "CKGG87",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발",
            "owner": "이상철",
            "remark": ""
        },
        {
            "no": "19",
            "name": "테스트 인디케이터",
            "spec": "0.01",
            "maker": "MITUTOYO",
            "serial": "TUM717",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 선반",
            "owner": "이상철",
            "remark": ""
        },
        {
            "no": "20",
            "name": "다이얼 게이지",
            "spec": "0~1mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "CAZE67",
            "buy": "2023-02-02",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "임미정",
            "remark": ""
        },
        {
            "no": "21",
            "name": "깊이 마이크로  미터",
            "spec": "0~25mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "919679",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "22",
            "name": "높이 게이지 (디지털형)",
            "spec": "0~300mm(0.01mm)",
            "maker": "MITUTOYO",
            "serial": "0000547",
            "buy": "2022-10-25",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실앞정반",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "23",
            "name": "높이 게이지 (수동)",
            "spec": "300mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "0312924",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "24",
            "name": "디지털 게이지",
            "spec": "0~12.7mm(0.001mm)",
            "maker": "MITUTOYO",
            "serial": "23103126",
            "buy": "2024-07-15",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "25",
            "name": "테스트 인디케이터",
            "spec": "1㎛",
            "maker": "MITUTOYO",
            "serial": "BJAW15",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "26",
            "name": "외측마이크로미터 (아날로그)",
            "spec": "75~100mm(0.01mm)",
            "maker": "MITUTOYO",
            "serial": "HJ3067",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "27",
            "name": "내측마이크로미터 (디지털형)",
            "spec": "18~35mm",
            "maker": "MITUTOYO",
            "serial": "738640",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "28",
            "name": "내측마이크로미터 (디지털형)",
            "spec": "50~100",
            "maker": "MITUTOYO",
            "serial": "851139",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        },
        {
            "no": "29",
            "name": "내외측 캘리퍼 (디지털형)",
            "spec": "(0~300)mm/0.01mm",
            "maker": "MITUTOYO",
            "serial": "25003",
            "buy": "",
            "disposal": "",
            "calib": "2025-07-05",
            "next": "2026-07-05",
            "loc": "개발 가공실",
            "owner": "이성현",
            "remark": ""
        }
    ]
}


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
