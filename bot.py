#!/usr/bin/env python3
"""
GradePoint Telegram Bot — Webster University + Standard grading
python-telegram-bot v21.x — plain text only
"""

import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")

# ── Conversation states ───────────────────────────────────────────────────────
COURSE_NAME, COURSE_PCT, COURSE_CREDITS = range(3)
PRIOR_GPA, PRIOR_CREDITS = range(10, 12)
SEMESTER_NAME = 20

# ── Grade scales ─────────────────────────────────────────────────────────────

# Webster University scale (exact from their official table)
WEBSTER_SCALE = [
    (94, "A",  4.0,  "Superior work"),
    (90, "A-", 3.67, "Superior work"),
    (87, "B+", 3.33, "Good work"),
    (83, "B",  3.0,  "Good work"),
    (80, "B-", 2.67, "Good work"),
    (77, "C+", 2.33, "Satisfactory work"),
    (73, "C",  2.0,  "Satisfactory work"),
    (70, "C-", 1.67, "Satisfactory work"),
    (65, "D+", 1.33, "Passing, but less than satisfactory"),
    (60, "D",  1.0,  "Passing, but less than satisfactory"),
    (0,  "F",  0.0,  "Failing"),
]

# Standard / Canvas scale
STANDARD_SCALE = [
    (97, "A+", 4.0),
    (93, "A",  4.0),
    (90, "A-", 3.7),
    (87, "B+", 3.3),
    (83, "B",  3.0),
    (80, "B-", 2.7),
    (77, "C+", 2.3),
    (73, "C",  2.0),
    (70, "C-", 1.7),
    (67, "D+", 1.3),
    (63, "D",  1.0),
    (60, "D-", 0.7),
    (0,  "F",  0.0),
]

def pct_to_grade(pct, mode="standard"):
    if mode == "webster":
        for minimum, letter, pts, _ in WEBSTER_SCALE:
            if pct >= minimum:
                return letter, pts
        return "F", 0.0
    else:
        for minimum, letter, pts in STANDARD_SCALE:
            if pct >= minimum:
                return letter, pts
        return "F", 0.0

def gpa_to_letter(gpa, mode="standard"):
    if mode == "webster":
        thresholds = [
            (3.85,"A"),(3.5,"A-"),(3.15,"B+"),(2.85,"B"),(2.6,"B-"),
            (2.15,"C+"),(1.85,"C"),(1.6,"C-"),(1.15,"D+"),(0.85,"D"),(0.01,"D-"),
        ]
    else:
        thresholds = [
            (3.85,"A"),(3.5,"A-"),(3.15,"B+"),(2.85,"B"),(2.5,"B-"),
            (2.15,"C+"),(1.85,"C"),(1.5,"C-"),(1.15,"D+"),(0.85,"D"),(0.01,"D-"),
        ]
    for t, l in thresholds:
        if gpa >= t:
            return l
    return "F"

def gpa_emoji(gpa):
    if gpa >= 3.7: return "🟢"
    if gpa >= 3.0: return "🔵"
    if gpa >= 2.0: return "🟡"
    if gpa >  0:   return "🟠"
    return "🔴"

def progress_bar(gpa, width=10):
    filled = round((gpa / 4.0) * width)
    return "█" * filled + "░" * (width - filled)

def get_user(ctx):
    if "courses"   not in ctx.user_data: ctx.user_data["courses"]   = []
    if "history"   not in ctx.user_data: ctx.user_data["history"]   = []
    if "prior"     not in ctx.user_data: ctx.user_data["prior"]     = None
    if "grademode" not in ctx.user_data: ctx.user_data["grademode"] = None  # "webster" or "standard"
    return ctx.user_data

def get_mode(ctx):
    return ctx.user_data.get("grademode", "standard")

def calc_semester_gpa(courses):
    tc = sum(c["credits"] for c in courses)
    tq = sum(c["pts"] * c["credits"] for c in courses)
    return (tq / tc if tc > 0 else None), tc, tq

def calc_true_gpa(ctx):
    ud = get_user(ctx)
    sem_gpa, sem_tc, sem_tq = calc_semester_gpa(ud["courses"])
    prior = ud["prior"]
    if sem_gpa is None and prior is None:
        return None
    total_credits = sem_tc + (prior["credits"] if prior else 0)
    total_qp      = sem_tq  + (prior["gpa"] * prior["credits"] if prior else 0)
    true_gpa = total_qp / total_credits if total_credits > 0 else 0.0
    return {"true_gpa": true_gpa, "sem_gpa": sem_gpa,
            "sem_tc": sem_tc, "prior": prior, "total_creds": total_credits}

def scale_info(mode):
    if mode == "webster":
        return (
            "Webster University Scale:\n"
            "A:  94-100%  (4.00) Superior\n"
            "A-: 90-93%   (3.67) Superior\n"
            "B+: 87-89%   (3.33) Good\n"
            "B:  83-86%   (3.00) Good\n"
            "B-: 80-82%   (2.67) Good\n"
            "C+: 77-79%   (2.33) Satisfactory\n"
            "C:  73-76%   (2.00) Satisfactory\n"
            "C-: 70-72%   (1.67) Satisfactory\n"
            "D+: 65-69%   (1.33) Passing\n"
            "D:  60-64%   (1.00) Passing\n"
            "F:  below 60% (0.00)"
        )
    else:
        return (
            "Standard / Canvas Scale:\n"
            "A+: 97-100%  (4.00)\n"
            "A:  93-96%   (4.00)\n"
            "A-: 90-92%   (3.70)\n"
            "B+: 87-89%   (3.30)\n"
            "B:  83-86%   (3.00)\n"
            "B-: 80-82%   (2.70)\n"
            "C+: 77-79%   (2.30)\n"
            "C:  73-76%   (2.00)\n"
            "C-: 70-72%   (1.70)\n"
            "D+: 67-69%   (1.30)\n"
            "D:  63-66%   (1.00)\n"
            "D-: 60-62%   (0.70)\n"
            "F:  below 60% (0.00)"
        )

# ── School selection ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    get_user(ctx)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏛 Webster University", callback_data="mode_webster"),
        InlineKeyboardButton("🌍 Other / International", callback_data="mode_standard"),
    ]])
    await update.message.reply_text(
        "🎓 Welcome to GradePoint Bot!\n\n"
        "I calculate your GPA using percentage scores and track your academic history.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "First — which grading system do you use?",
        reply_markup=keyboard,
    )

async def cb_mode_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = "webster" if query.data == "mode_webster" else "standard"
    ctx.user_data["grademode"] = mode
    get_user(ctx)

    if mode == "webster":
        label = "Webster University"
        note  = "Using Webster's official grading scale (A=94-100, A-=90-93, etc.)"
    else:
        label = "Standard / International"
        note  = "Using the standard Canvas grading scale (A=93-100, A-=90-92, etc.)"

    await query.edit_message_text(
        f"✅ Grading system set to: {label}\n"
        f"{note}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "Commands:\n"
        "  /add      — Add a course\n"
        "  /gpa      — See your GPA\n"
        "  /prior    — Enter previous GPA\n"
        "  /done     — Save this semester\n"
        "  /history  — View saved semesters\n"
        "  /scale    — View grade scale\n"
        "  /switch   — Switch grading system\n"
        "  /clear    — Clear current courses\n"
        "  /reset    — Full reset\n"
        "  /help     — Full guide\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Start by typing /add to add your first course!"
    )

async def cmd_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Let user switch grading system anytime."""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏛 Webster University", callback_data="mode_webster"),
        InlineKeyboardButton("🌍 Other / International", callback_data="mode_standard"),
    ]])
    current = get_mode(ctx)
    current_label = "Webster University" if current == "webster" else "Standard / International"
    await update.message.reply_text(
        f"Current system: {current_label}\n\n"
        "Switch to a different grading system?\n"
        "(Note: this won't change already-saved semesters)",
        reply_markup=keyboard,
    )

def check_mode(ctx):
    """Returns mode, or None if not set yet."""
    return ctx.user_data.get("grademode", None)

async def require_mode(update, ctx):
    """If no mode selected, prompt user to pick one. Returns False if blocked."""
    if not check_mode(ctx):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🏛 Webster University", callback_data="mode_webster"),
            InlineKeyboardButton("🌍 Other / International", callback_data="mode_standard"),
        ]])
        await update.message.reply_text(
            "Please select your grading system first:",
            reply_markup=keyboard,
        )
        return False
    return True

# ── /scale command ────────────────────────────────────────────────────────────

async def cmd_scale(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    mode = get_mode(ctx)
    await update.message.reply_text(
        "📊 Grade Scale Reference\n\n" + scale_info(mode)
    )

# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    mode = get_mode(ctx)
    label = "Webster University" if mode == "webster" else "Standard / International"
    await update.message.reply_text(
        f"📖 GradePoint Bot — Full Guide\n"
        f"Current grading system: {label}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "Step 1 — Add courses:\n"
        "Use /add for each course. You will enter:\n"
        "  • Course name (e.g. Math 101)\n"
        "  • Score as a percentage (e.g. 91.5)\n"
        "  • Credit hours (e.g. 3)\n\n"
        "Step 2 — Check your GPA:\n"
        "Use /gpa to see your semester GPA and full breakdown.\n\n"
        "Step 3 — Add prior history:\n"
        "Use /prior to enter your GPA and credits from previous semesters "
        "to see your TRUE cumulative GPA.\n\n"
        "Step 4 — Save the semester:\n"
        "Use /done to name and save the semester.\n\n"
        "Step 5 — View history:\n"
        "Use /history to see all saved semesters.\n\n"
        "Use /switch to change grading system anytime.\n"
        "Use /scale to view the full grade scale.\n"
    )

# ── /gpa ─────────────────────────────────────────────────────────────────────

async def cmd_gpa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud   = get_user(ctx)
    mode = get_mode(ctx)
    courses = ud["courses"]
    msg = update.message or (update.callback_query and update.callback_query.message)

    if not courses:
        await msg.reply_text("📭 No courses added yet.\nUse /add to add your first course!")
        return

    sem_gpa, tc, tq = calc_semester_gpa(courses)
    prior  = ud["prior"]
    result = calc_true_gpa(ctx)

    mode_label = "Webster University" if mode == "webster" else "Standard"
    lines = [f"📚 Current Semester Courses ({mode_label} scale):\n"]
    for i, c in enumerate(courses, 1):
        lines.append(
            f"  {i}. {c['name']}\n"
            f"     Score: {c['pct']}% => {c['letter']} ({c['pts']:.2f} pts) | {c['credits']} cr"
        )

    sem_letter = gpa_to_letter(sem_gpa, mode)
    sem_bar    = progress_bar(sem_gpa)
    lines.append(
        f"\n━━━━━━━━━━━━━━━━\n"
        f"📊 This Semester:\n"
        f"  GPA: {sem_gpa:.2f} / 4.00  {gpa_emoji(sem_gpa)}\n"
        f"  Grade: {sem_letter}\n"
        f"  Progress: {sem_bar} {sem_gpa:.2f}\n"
        f"  Credits: {tc} | Quality pts: {tq:.2f}"
    )

    if prior and result:
        tg = result["true_gpa"]
        t_letter = gpa_to_letter(tg, mode)
        t_bar    = progress_bar(tg)
        lines.append(
            f"\n━━━━━━━━━━━━━━━━\n"
            f"⭐ True Cumulative GPA:\n"
            f"  GPA: {tg:.2f} / 4.00  {gpa_emoji(tg)}\n"
            f"  Grade: {t_letter}\n"
            f"  Progress: {t_bar} {tg:.2f}\n"
            f"  Total credits: {result['total_creds']:.0f}\n\n"
            f"  (Prior: {prior['gpa']:.2f} GPA, {prior['credits']:.0f} cr  +  "
            f"This sem: {sem_gpa:.2f} GPA, {tc:.0f} cr)"
        )
    else:
        lines.append(
            "\n💡 Tip: Use /prior to add your previous GPA and see your true cumulative GPA!"
        )

    await msg.reply_text("\n".join(lines))

# ── /history ──────────────────────────────────────────────────────────────────

async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud      = get_user(ctx)
    mode    = get_mode(ctx)
    history = ud["history"]
    if not history:
        await update.message.reply_text(
            "📭 No saved semesters yet.\nUse /add then /done to save one!"
        )
        return

    total_c = sum(s["tc"] for s in history)
    total_q = sum(s["tq"] for s in history)
    cum_gpa = total_q / total_c if total_c > 0 else 0.0

    icons = ["🎓","📖","🌿","⭐","🔬","🎯","💡","📐","🏛","✨"]
    lines = ["🗂 Semester History\n━━━━━━━━━━━━━━━━\n"]

    for i, sem in enumerate(reversed(history)):
        icon   = icons[i % len(icons)]
        s_mode = sem.get("mode", mode)
        letter = gpa_to_letter(sem["gpa"], s_mode)
        lines.append(
            f"{icon} {sem['name']}\n"
            f"   GPA: {sem['gpa']:.2f} ({letter}) {gpa_emoji(sem['gpa'])} | {sem['tc']} credits\n"
        )
        for c in sem["courses"]:
            lines.append(f"   • {c['name']}: {c['pct']}% => {c['letter']} ({c['credits']} cr)")
        lines.append("")

    lines.append(
        f"━━━━━━━━━━━━━━━━\n"
        f"📈 Cumulative GPA: {cum_gpa:.2f} {gpa_emoji(cum_gpa)}\n"
        f"   Total credits: {total_c}"
    )
    await update.message.reply_text("\n".join(lines))

# ── /clear and /reset ─────────────────────────────────────────────────────────

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = get_user(ctx)
    count = len(ud["courses"])
    ud["courses"] = []
    await update.message.reply_text(
        f"🗑 Cleared {count} course(s) from the current semester.\nUse /add to start fresh!"
    )

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes, reset everything", callback_data="confirm_reset"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_reset"),
    ]])
    await update.message.reply_text(
        "⚠️ Are you sure?\n\nThis will delete all your courses, history, and prior GPA.",
        reply_markup=keyboard,
    )

async def cb_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_reset":
        ctx.user_data.clear()
        get_user(ctx)
        await query.edit_message_text("✅ Everything has been reset. Use /start to begin again!")
    else:
        await query.edit_message_text("❌ Reset cancelled.")

# ── Add Course Conversation ───────────────────────────────────────────────────

async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await require_mode(update, ctx):
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 Add a new course\n\n"
        "Step 1 of 3 — What is the course name?\n"
        "(e.g. Mathematics 101, English, Physics)\n\n"
        "Send /cancel to stop.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return COURSE_NAME

async def add_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Please enter a valid course name.")
        return COURSE_NAME
    ctx.user_data["_tmp"] = {"name": name}
    await update.message.reply_text(
        f"✅ Course: {name}\n\n"
        "Step 2 of 3 — What is your percentage score?\n"
        "(e.g. 91.5 — just the number, no % sign)"
    )
    return COURSE_PCT

async def add_pct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        pct = float(update.message.text.strip().replace("%", ""))
        if not (0 <= pct <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid percentage between 0 and 100.\n(e.g. 87.5)"
        )
        return COURSE_PCT

    mode = get_mode(ctx)
    letter, pts = pct_to_grade(pct, mode)
    ctx.user_data["_tmp"]["pct"]    = pct
    ctx.user_data["_tmp"]["letter"] = letter
    ctx.user_data["_tmp"]["pts"]    = pts

    keyboard = ReplyKeyboardMarkup(
        [["1", "2", "3"], ["4", "5", "6"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text(
        f"✅ Score: {pct}% => {letter} ({pts:.2f} GPA points)\n\n"
        "Step 3 of 3 — How many credit hours is this course?\n"
        "(e.g. 3 — tap a button or type the number)",
        reply_markup=keyboard,
    )
    return COURSE_CREDITS

async def add_credits(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        credits = float(update.message.text.strip())
        if credits <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number of credits (e.g. 3).")
        return COURSE_CREDITS

    course = ctx.user_data.pop("_tmp", {})
    course["credits"] = credits
    ud = get_user(ctx)
    ud["courses"].append(course)

    sem_gpa, tc, _ = calc_semester_gpa(ud["courses"])
    count = len(ud["courses"])

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Add another course", callback_data="add_another"),
        InlineKeyboardButton("📊 See GPA", callback_data="see_gpa"),
    ]])

    await update.message.reply_text(
        f"✅ {course['name']} added!\n\n"
        f"  Score: {course['pct']}% => {course['letter']} ({course['pts']:.2f} pts)\n"
        f"  Credits: {credits}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Courses this semester: {count}\n"
        f"Current GPA: {sem_gpa:.2f} {gpa_emoji(sem_gpa)}\n"
        f"Total credits: {tc}",
        reply_markup=keyboard,
    )
    return ConversationHandler.END

async def cb_add_another(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📝 Add another course\n\nStep 1 of 3 — What is the course name?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return COURSE_NAME

async def cb_see_gpa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await cmd_gpa(update, ctx)

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("_tmp", None)
    ctx.user_data.pop("_tmp_prior", None)
    await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── Prior GPA Conversation ────────────────────────────────────────────────────

async def cmd_prior(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await require_mode(update, ctx):
        return ConversationHandler.END
    ud = get_user(ctx)
    existing = ud["prior"]
    note = ""
    if existing:
        note = f"\nCurrent prior GPA: {existing['gpa']:.2f} | {existing['credits']:.0f} credits\nSending new values will overwrite this.\n"
    await update.message.reply_text(
        "🏛 Previous Academic History\n\n"
        f"{note}"
        "Step 1 of 2 — What is your cumulative GPA from BEFORE this semester?\n"
        "(e.g. 3.45 — a number between 0.00 and 4.00)\n\n"
        "Send /cancel to stop.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PRIOR_GPA

async def prior_gpa_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gpa = float(update.message.text.strip())
        if not (0.0 <= gpa <= 4.0):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid GPA between 0.00 and 4.00.\n(e.g. 3.45)"
        )
        return PRIOR_GPA
    ctx.user_data["_tmp_prior"] = {"gpa": gpa}
    await update.message.reply_text(
        f"✅ Prior GPA: {gpa:.2f}\n\n"
        "Step 2 of 2 — How many total credits did you earn before this semester?\n"
        "(e.g. 60 — you can find this on your transcript)"
    )
    return PRIOR_CREDITS

async def prior_credits_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        credits = float(update.message.text.strip())
        if credits < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number of credits (e.g. 60).")
        return PRIOR_CREDITS

    tmp = ctx.user_data.pop("_tmp_prior", {})
    prior_g = tmp["gpa"]
    ud = get_user(ctx)
    ud["prior"] = {"gpa": prior_g, "credits": credits}
    mode = get_mode(ctx)

    result = calc_true_gpa(ctx)
    extra = ""
    if result and result["sem_gpa"] is not None:
        tg = result["true_gpa"]
        extra = (
            f"\n━━━━━━━━━━━━━━━━\n"
            f"⭐ Your True Cumulative GPA: {tg:.2f} {gpa_emoji(tg)}\n"
            f"   Grade: {gpa_to_letter(tg, mode)}\n"
            f"   Total credits: {result['total_creds']:.0f}"
        )
    else:
        extra = "\n\nUse /add to add your current courses and see your true GPA!"

    await update.message.reply_text(
        f"✅ Prior history saved!\n\n"
        f"  Prior GPA: {prior_g:.2f}\n"
        f"  Prior credits: {credits:.0f}"
        f"{extra}",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

# ── Save Semester Conversation ────────────────────────────────────────────────

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = get_user(ctx)
    if not ud["courses"]:
        await update.message.reply_text("📭 No courses to save yet. Use /add first!")
        return ConversationHandler.END

    sem_gpa, tc, _ = calc_semester_gpa(ud["courses"])
    count   = len(ud["courses"])
    sem_num = len(ud["history"]) + 1

    await update.message.reply_text(
        f"💾 Save this semester?\n\n"
        f"  Courses: {count} | Credits: {tc} | GPA: {sem_gpa:.2f} {gpa_emoji(sem_gpa)}\n\n"
        f"What would you like to name this semester?\n"
        f"(e.g. Fall 2024, Spring 2025 — or type anything)\n"
        f"Default name will be: Semester {sem_num}\n\n"
        "Send /cancel to go back."
    )
    return SEMESTER_NAME

async def save_semester_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud   = get_user(ctx)
    mode = get_mode(ctx)
    name = update.message.text.strip()
    sem_num = len(ud["history"]) + 1
    if not name:
        name = f"Semester {sem_num}"

    sem_gpa, tc, tq = calc_semester_gpa(ud["courses"])

    ud["history"].append({
        "name": name, "gpa": sem_gpa, "tc": tc, "tq": tq, "mode": mode,
        "courses": [
            {"name": c["name"], "pct": c["pct"], "letter": c["letter"], "credits": c["credits"]}
            for c in ud["courses"]
        ],
    })

    old_prior = ud["prior"]
    if old_prior:
        new_tc  = old_prior["credits"] + tc
        new_tq  = old_prior["gpa"] * old_prior["credits"] + tq
        new_gpa = new_tq / new_tc
        ud["prior"] = {"gpa": new_gpa, "credits": new_tc}
        prior_note = (
            f"\n✅ Your prior GPA updated to {new_gpa:.2f} "
            f"({new_tc:.0f} total credits) for next semester."
        )
    else:
        prior_note = "\n💡 Tip: Next semester, use /prior to carry this GPA forward!"

    ud["courses"] = []

    await update.message.reply_text(
        f"🎉 '{name}' saved successfully!\n\n"
        f"  GPA: {sem_gpa:.2f} {gpa_emoji(sem_gpa)} | Credits: {tc}"
        f"{prior_note}\n\n"
        f"Use /history to view all your semesters."
    )
    return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add", cmd_add),
            CallbackQueryHandler(cb_add_another, pattern="^add_another$"),
        ],
        states={
            COURSE_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            COURSE_PCT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pct)],
            COURSE_CREDITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_credits)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    prior_conv = ConversationHandler(
        entry_points=[CommandHandler("prior", cmd_prior)],
        states={
            PRIOR_GPA:     [MessageHandler(filters.TEXT & ~filters.COMMAND, prior_gpa_handler)],
            PRIOR_CREDITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, prior_credits_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    done_conv = ConversationHandler(
        entry_points=[CommandHandler("done", cmd_done)],
        states={
            SEMESTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_semester_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(add_conv)
    app.add_handler(prior_conv)
    app.add_handler(done_conv)

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("gpa",     cmd_gpa))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("clear",   cmd_clear))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("scale",   cmd_scale))
    app.add_handler(CommandHandler("switch",  cmd_switch))

    app.add_handler(CallbackQueryHandler(cb_mode_select, pattern="^mode_(webster|standard)$"))
    app.add_handler(CallbackQueryHandler(cb_reset,       pattern="^(confirm|cancel)_reset$"))
    app.add_handler(CallbackQueryHandler(cb_see_gpa,     pattern="^see_gpa$"))

    logger.info("GradePoint Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
