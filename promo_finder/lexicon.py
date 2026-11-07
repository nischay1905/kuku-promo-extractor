"""Small, editable lexicons. Kept generic to the melodrama genre, not to one show."""
import re

def _rx(words: str) -> re.Pattern:
    return re.compile(r"\b(?:" + words + r")\b", re.I)

# --- delivery / emotion tags on dialogue labels -> intensity 0..1 ---------------------------------
TAG_WEIGHTS = {
    1.0: r"scream\w*|shout\w*|shriek\w*|roar\w*|bellow\w*|thunder\w*|hysteric\w*|maniac\w*|enraged|livid|furious|outraged|explosive",
    0.8: r"venom\w*|vicious|lethal|menac\w*|threaten\w*|accus\w*|fierce|savage|murderous|seething|barking|snarl\w*|sadistic",
    0.65: r"desperate|panick\w*|terrif\w*|horrif\w*|stunned|shocked|gasp\w*|sobb\w*|wail\w*|frantic|defiant|cruel|chilling|ominous|dangerous|triumphant|gloat\w*|incredulous",
    0.5: r"mock\w*|taunt\w*|cold|sinister|sneer\w*|scorn\w*|contempt\w*|pleading|begging|weeping|tearful|anguish\w*|resolute|commanding|imperious|urgent",
    0.3: r"firm|steady|stern|grave|sharp|dismissive|smug|bitter|determined|solemn",
    0.15: r"soft\w*|gentle|tender|warm|quiet|calm|peaceful|sweet|reassuring|grateful|loving|fond|serene|humble|hushed",
}
TAG_RX = [(w, _rx(p)) for w, p in TAG_WEIGHTS.items()]

# --- words that make a line a stronger hook / cliffhanger ------------------------------------------
STRONG = _rx(r"kill\w*|dead|die[sd]?|death|murder\w*|hang\w*|gallows|noose|execut\w+|poison\w*|arsenic|witch\w*|traitor\w*|treason\w*|"
             r"betray\w*|disown\w*|abandon\w*|humiliat\w*|imposter|impostor|alive|secret|truth|lie[sd]?|liar|"
             r"arrest\w*|dungeon|burn\w*|stole\w*|steal\w*|thief|blood|scar\w*")
MEDIUM = _rx(r"husband|wife|marry|married|marrying|wedding|bride|groom|altar|duke|duchess|sister|father|mother|family|"
             r"prison\w*|chains?|guards?|trial|judge|magistrate|vow|swear|never|nothing|everything|"
             r"who|why|how dare|you dare|take your hands off|get out|silence|enough|stop|leave|mercy")
ACCUSE = re.compile(r"\byou (knew|dare|lied|chose|took|stole|did|are|will|have|let|planted|poisoned|tortured|sold)\b", re.I)

# --- visual / audio shock in ACTION, CAMERA, SOUND FX text -----------------------------------------
SHOCK = {
    1.0: r"slaps?|slapp\w+|strikes?|struck|slams?|slamm\w+|smash\w*|crash\w*|explo\w+|detonat\w+|fireball|shatter\w*|"
         r"hurl\w*|fling\w*|flings|wrench\w*|snatch\w*|rips?|ripp\w+|tackl\w+|lung\w+|bursts?|burst\w+",
    0.8: r"blood\w*|poker|branding|whip\w*|riding crop|dagger|sword|pistol|gun|noose|fire|flames?|inferno|"
         r"drags?|dragg\w+|collaps\w+|shove\w*|thrust\w*|kneel\w*|one knee|reveal\w*|unmask\w*|freez\w+|froze",
    0.5: r"gasps?|scream\w*|recoil\w*|chains?|shackle\w*|trembl\w*|weeping|sobb\w*|points?|pointing",
}
SHOCK_RX = [(w, re.compile(r"\b(?:" + p + r")\b", re.I)) for w, p in SHOCK.items()]

CLIFF_MARKER = re.compile(
    r"cliffhanger|cuts?(?:ting)? (?:sharply |abruptly |straight )?to black|cut to black|freeze[- ]?frame|"
    r"scene freezes|frame holds|holds? on|hang\w* in|final cut|abrupt cut|sting\b|crescendo|"
    r"swell\w* (?:into|to)|ominous|heart-stopping|suspens\w+", re.I)
TENSION = _rx(r"ominous|menac\w*|dread|terror|terrif\w*|shock\w*|gasp\w*|freez\w+|froze|scream\w*|threat\w*|sinister|murderous|"
              r"venom\w*|trapped|horrif\w*|panick\w*|lethal|deadly|vengeance|fury|rage|looming|suspens\w*|stunned|petrified|"
              r"smirk\w*|triumphant|wicked|predatory")
WARM = _rx(r"warm\w*|peace\w*|tender\w*|gentle|gently|softly|content\w*|serene|loving|affection\w*|laugh\w*|relie\w*|"
           r"grateful|gratitude|safe\w*|embrac\w*|cradl\w*|fade[sd]? out|fading out|lullaby|hopeful|radiant|bask\w*|sunlight|fades? into silence")
RESOLUTION = re.compile(r"\b(thank you|i accept|i do\b|i love you|rest now|goodnight|forgive|together|i am sorry|i'm sorry|"
                        r"tomorrow, we begin again|it is enough|there\.)", re.I)

# --- premise / stakes cues (does the clip explain itself?) -----------------------------------------
PREMISE = _rx(r"husband|wife|wedding|altar|marry|married|sister|father|mother|family|disowned?|duke|duchess|poison\w*|arsenic|witch\w*|"
              r"hang\w*|gallows|execut\w+|trial|dungeon|prison\w*|betray\w*|inherit\w*|dowry|ledger|locket|healer|"
              r"abandon\w*|chose|choose|worth")

# --- platform-safety flags (editor review, not auto-reject) ----------------------------------------
SEXUAL = re.compile(r"bare chest|shirtless|naked|chemise|passionate embrace|intimate, passionate|carnal|forbidden entanglement|"
                    r"unkempt bed|in bed|pulls? (?:catherine|her|him) into a fierce", re.I)
VIOLENT = re.compile(r"\bblood\w*|torture\w*|branding|poker|whip\b|riding crop|strangl\w+|throat|noose|gallows|stabbing|"
                     r"slice[sd]? through flesh|lacerat\w+|gash\w*|hot iron|red-hot", re.I)
