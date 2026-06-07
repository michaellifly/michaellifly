"""
Recommendation engine.

Maps detected patterns to actionable, evidence-based suggestions.
Each recommendation includes a priority (1=urgent, 2=important, 3=nice-to-have),
a short title, and a detailed explanation with practical steps.
"""

from dataclasses import dataclass
from typing import Optional

from analysis.patterns import Pattern
from analysis.sleep_analyzer import SleepStats


@dataclass
class Recommendation:
    priority: int           # 1 = urgent, 2 = important, 3 = info
    title: str
    summary: str
    action_steps: list[str]
    pattern_name: Optional[str] = None

    @property
    def priority_label(self) -> str:
        return {1: "URGENT", 2: "IMPORTANT", 3: "INFO"}.get(self.priority, "INFO")


PATTERN_RECS: dict[str, Recommendation] = {
    "Early Wake Streak": Recommendation(
        priority=1,
        title="Shift Bedtime Earlier by 15–30 Minutes",
        summary=(
            "Counterintuitive but effective: earlier bedtime reduces early morning waking. "
            "Overtiredness raises cortisol, which acts as an alarm clock around 4–6 AM."
        ),
        action_steps=[
            "Move bedtime 15–20 minutes earlier for 3 nights in a row.",
            "Darken the room completely — even small light cues (sunrise) wake babies early.",
            "Use white noise to mask environmental sounds at dawn.",
            "Hold off on getting baby until at least 6:00–6:30 AM, even if she stirs — "
            "responding before 6 AM can reinforce the early wake as a 'start of day' signal.",
        ],
        pattern_name="Early Wake Streak",
    ),
    "Frequent Early Waking": Recommendation(
        priority=2,
        title="Audit the Sleep Environment for Early Morning Light/Noise",
        summary="Light and sound around sunrise are the most common triggers for early waking.",
        action_steps=[
            "Install blackout curtains or blinds — the room should be near-dark even at 7 AM.",
            "Add or increase white noise volume (aim for ~65 dB, roughly the sound of a shower).",
            "Check if garbage trucks, birds, or traffic occur around the wake time.",
        ],
        pattern_name="Frequent Early Waking",
    ),
    "Very Early Waking (<5 AM)": Recommendation(
        priority=1,
        title="Rule Out Hunger and Physical Comfort",
        summary="Before 5 AM wakes are often hunger-driven, especially in younger babies.",
        action_steps=[
            "Ensure the last feed is adequate before bed.",
            "Check room temperature — ideal is 68–72°F (20–22°C).",
            "For babies 6+ months: consider a 'dream feed' at 10–11 PM to extend night sleep.",
        ],
        pattern_name="Very Early Waking (<5 AM)",
    ),
    "Wake Time Drifting Earlier": Recommendation(
        priority=2,
        title="Gradually Reset Wake Time Over 1–2 Weeks",
        summary="A slow shift preserves sleep pressure while moving the body clock forward.",
        action_steps=[
            "Shift bedtime 10 minutes later every 2–3 days while keeping nap times consistent.",
            "Expose baby to bright morning light after 7 AM to anchor the circadian clock.",
            "Avoid going in the room before your target wake time — even quiet presence signals day.",
        ],
        pattern_name="Wake Time Drifting Earlier",
    ),
    "Significant Sleep Debt": Recommendation(
        priority=1,
        title="Prioritize Total Sleep — Add a Nap or Extend Night Sleep",
        summary="Chronically under-slept babies become overtired, sleep lighter, and wake earlier.",
        action_steps=[
            "Add a short (30–45 min) bridging nap if baby is refusing a longer one.",
            "Move bedtime earlier by up to 1 hour temporarily to repay sleep debt.",
            "Reduce stimulation in the hour before all sleep periods.",
        ],
        pattern_name="Significant Sleep Debt",
    ),
    "Mild Sleep Deficit": Recommendation(
        priority=2,
        title="Protect Nap Time and Ensure an Age-Appropriate Bedtime",
        summary="Even a small daily deficit accumulates over a week.",
        action_steps=[
            "Guard nap windows — avoid errands or outings that push naps late.",
            "Aim for a bedtime that gives 11–12h of night-sleep opportunity.",
        ],
        pattern_name="Mild Sleep Deficit",
    ),
    "Declining Sleep Trend": Recommendation(
        priority=2,
        title="Investigate Recent Schedule Changes",
        summary="A week-over-week drop in total sleep usually has a cause.",
        action_steps=[
            "Review whether a nap was recently dropped or shortened.",
            "Check for teething, illness, or developmental leaps (sleep regressions).",
            "Return to the last schedule that worked well.",
        ],
        pattern_name="Declining Sleep Trend",
    ),
    "Late Bedtime": Recommendation(
        priority=2,
        title="Move Bedtime to 7:00–8:00 PM",
        summary="A bedtime past 8:30–9 PM is one of the strongest predictors of early morning waking.",
        action_steps=[
            "Start the bedtime routine 30–45 minutes before target sleep time.",
            "Use consistent cues: dim lights, bath, feed, white noise.",
            "Shift in 15-minute increments over a week if a large jump feels disruptive.",
        ],
        pattern_name="Late Bedtime",
    ),
    "Inconsistent Bedtime": Recommendation(
        priority=2,
        title="Establish a Consistent Bedtime (±15 Minutes)",
        summary="The circadian clock thrives on regularity. Variability confuses sleep drive.",
        action_steps=[
            "Pick a target bedtime and aim to be within 15 minutes every night.",
            "Keep the bedtime routine identical (same order, same duration) each night.",
            "On busy days, shorten the routine but keep the bedtime consistent.",
        ],
        pattern_name="Inconsistent Bedtime",
    ),
    "Bedtime Creeping Later": Recommendation(
        priority=3,
        title="Check for Overtiredness at Nap Transition",
        summary="Bedtime often drifts later when a nap is dropped before baby is ready.",
        action_steps=[
            "Temporarily re-introduce a short late-afternoon nap (30 min) if needed.",
            "Or offer an earlier bedtime (6:30–7:00 PM) to compensate for the lost nap sleep.",
        ],
        pattern_name="Bedtime Creeping Later",
    ),
    "Too Few Naps": Recommendation(
        priority=2,
        title="Reintroduce a Missed Nap",
        summary="Skipping naps at this age leads to overtiredness, which paradoxically disrupts night sleep.",
        action_steps=[
            "Offer a second nap opportunity even if baby doesn't always take it.",
            "Watch for tired cues (eye rubbing, yawning, pulling ears) and act quickly.",
        ],
        pattern_name="Too Few Naps",
    ),
    "Missing Nap": Recommendation(
        priority=2,
        title="Protect the Single Daily Nap",
        summary="At this age one solid nap (1.5–2.5h) sustains good night sleep.",
        action_steps=[
            "Offer the nap at the same time each day (typically 12:00–1:00 PM).",
            "Use the same sleep cues as night (dark room, white noise, same music).",
        ],
        pattern_name="Missing Nap",
    ),
    "Short Naps Linked to Early Waking": Recommendation(
        priority=2,
        title="Work on Nap Lengthening",
        summary="Short naps (<45 min) indicate the baby is waking at the end of a sleep cycle and not connecting to the next.",
        action_steps=[
            "Stay nearby at the 35–40 minute mark and provide gentle settling before she fully wakes.",
            "Try a 'nap cap': if baby wakes, allow 5–10 minutes of fussing before intervening.",
            "Ensure wake window before nap is correct — both under- and over-tiredness shorten naps.",
        ],
        pattern_name="Short Naps Linked to Early Waking",
    ),
    "Last Wake Window Too Long": Recommendation(
        priority=1,
        title="Shorten the Last Wake Window Before Bed",
        summary=(
            "An overly long last wake window is the #1 mechanical cause of early morning waking. "
            "Overtired babies enter light sleep sooner and can't re-settle at 4–6 AM."
        ),
        action_steps=[
            "Move bedtime earlier so the last wake window hits the top of the recommended range.",
            "Watch for tired cues and respond — don't wait for a set clock time if baby is already tired.",
            "Avoid stimulating activities (screens, rough play) in the last 30 minutes of the wake window.",
        ],
        pattern_name="Last Wake Window Too Long",
    ),
}

GENERAL_RECS = [
    Recommendation(
        priority=3,
        title="Log Consistently for 2+ Weeks",
        summary="The more complete the data, the more reliable the patterns.",
        action_steps=[
            "Record every sleep start/end in Baby Tracker, including brief car-seat naps.",
            "Note any unusual events (travel, illness, leap) as comments.",
        ],
    ),
]


class RecommendationEngine:
    def __init__(self, patterns: list[Pattern], stats: SleepStats):
        self.patterns = patterns
        self.stats = stats

    def generate(self) -> list[Recommendation]:
        recs = []
        seen_titles = set()

        for pattern in self.patterns:
            rec = PATTERN_RECS.get(pattern.name)
            if rec and rec.title not in seen_titles:
                recs.append(rec)
                seen_titles.add(rec.title)

        # Always add general recommendation if data window is short
        if len(self.patterns) == 0:
            recs.extend(GENERAL_RECS)

        return sorted(recs, key=lambda r: r.priority)
