"""Spell-IDs (Warlock, Midnight 12.1). Ausschließlich IDs matchen, nie Namen.

Die IDs wurden aus `masterData.abilities` des Referenz-Reports qCZ2bPkFVzgc46Lp
ermittelt (Namen nur als Kommentar). Unbekannte Cast-IDs werden geloggt, nicht geraten.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- Demonology
HAND_OF_GULDAN = 105174  # Hand of Gul'dan
SHADOW_BOLT = 686  # Shadow Bolt
DEMONBOLT = 264178  # Demonbolt
IMPLOSION = 196277  # Implosion (Cast); Schaden läuft unter 196278
IMPLOSION_DAMAGE = 196278
ISOLATED_IMPLOSION = 1306077  # Isolated Implosion (Schaden)
CALL_DREADSTALKERS = 104316  # Call Dreadstalkers
SUMMON_DEMONIC_TYRANT = 265187  # Summon Demonic Tyrant
GRIMOIRE_IMP_LORD = 1276452  # Grimoire: Imp Lord
INFERNAL_BOLT = 434506  # Infernal Bolt (Diabolist, ersetzt Shadow Bolt nach Ruination-Fenster)
RUINATION = 434635  # Ruination
POWER_SIPHON = 264130  # Power Siphon
DEMONIC_STRENGTH = 267171  # Demonic Strength
SUMMON_VILEFIEND = 264119  # Summon Vilefiend
BILESCOURGE_BOMBERS = 267211  # Bilescourge Bombers
GUILLOTINE = 386833  # Guillotine
DOOM = 603  # Doom
DIABOLIC_RITUAL = 428514  # Diabolic Ritual (Schaden der Rituale)
DOMINION_OF_ARGUS = 1276222  # Dominion of Argus (Schaden der Argus-Dämonen, Sammel-ID)
WILD_IMP_HOG_SUMMON = 104317  # Summon-Event Wild Imp aus Hand of Gul'dan
WILD_IMP_INNER_DEMONS_SUMMON = 279910  # Summon-Event Wild Imp aus Inner Demons
FEL_FIREBOLT = 104318  # Fel Firebolt (Wild Imp)

# Buffs (targetID = Spieler)
DEMONIC_CORE_BUFF = 264173  # Demonic Core
DEMONIC_POWER_BUFF = 265273  # Demonic Power (Tyrant aktiv)
DOMINION_OF_ARGUS_BUFF = 1276222  # Dominion-Portal-Fenster (gleiche ID wie Schaden)

# --------------------------------------------------------------------------- Destruction
INCINERATE = 29722  # Incinerate
CHAOS_BOLT = 116858  # Chaos Bolt
CONFLAGRATE = 17962  # Conflagrate
SHADOWBURN = 17877  # Shadowburn
WITHER = 445468  # Wither (Hellcaller, ersetzt Immolate)
IMMOLATE = 348  # Immolate
HAVOC = 80240  # Havoc
SOUL_FIRE = 6353  # Soul Fire
MALEVOLENCE = 442726  # Malevolence
SUMMON_INFERNAL = 1122  # Summon Infernal
RAIN_OF_FIRE = 5740  # Rain of Fire
CATACLYSM = 152108  # Cataclysm
CHANNEL_DEMONFIRE = 196447  # Channel Demonfire
DIMENSIONAL_RIFT = 387976  # Dimensional Rift
BLACKENED_SOUL = 445936  # Blackened Soul (Hellcaller-Schaden)

# Buffs
BACKDRAFT_BUFF = 117828  # Backdraft
FIENDISH_CRUELTY_BUFF = 456745  # Fiendish Cruelty (Shadowburn-Proc), ID aus Vergleichslogs prüfen
MALEVOLENCE_BUFF = 442726

# --------------------------------------------------------------------------- Utility
# Alles hier zählt NICHT als Spieler-Cast (Rotationszähler, Lücken, Casts/30 s).
UTILITY: frozenset[int] = frozenset(
    {
        108416,  # Dark Pact
        104773,  # Unending Resolve
        111400,  # Burning Rush
        48018,  # Demonic Circle
        48020,  # Demonic Circle: Teleport
        6789,  # Mortal Coil
        385899,  # Soulburn
        30283,  # Shadowfury
        5782,  # Fear
        710,  # Banish
        1714,  # Curse of Tongues
        702,  # Curse of Weakness
        334275,  # Curse of Exhaustion
        234153,  # Drain Life
        755,  # Health Funnel
        5697,  # Unending Breath
        698,  # Ritual of Summoning
        29893,  # Create Soulwell
        6201,  # Create Healthstone
        6262,  # Healthstone
        452930,  # Demonic Healthstone
        20707,  # Soulstone
        333889,  # Fel Domination
        119898,  # Command Demon
        688,  # Summon Imp
        697,  # Summon Voidwalker
        712,  # Summon Succubus/Sayaad
        691,  # Summon Felhunter
        30146,  # Summon Felguard
        366222,  # Summon Sayaad
        1295247,  # Concentrated Silvermoon Health Potion
        1293316,  # Empowering Venom (Raid-Buff-Proc)
        1236616,  # Light's Potential (Raid-Buff-Proc)
        # Racials
        265221,  # Fireblood
        28730,  # Arcane Torrent
        59752,  # Will to Survive
        20572,  # Blood Fury
        26297,  # Berserking
        33702,  # Blood Fury (Spell)
        58984,  # Shadowmeld
        69041,  # Rocket Barrage
        69070,  # Rocket Jump
        # Set-/Trinket-Procs, die als Cast auftauchen
        1302265,  # Omnium Folio
    }
)

# Zählt nicht als Spieler-Cast, obwohl es ein GCD-Zauber ist: Havoc.
# Grund: Die per Hand ermittelten Referenzwerte (282 Casts, 29 Lücken / 101 s auf Fight 17)
# stimmen nur ohne Havoc. Wird als eigene Destro-Metrik ausgewertet.
NOT_COUNTED: frozenset[int] = frozenset({HAVOC})

EXCLUDED_FROM_PLAYER_CASTS: frozenset[int] = UTILITY | NOT_COUNTED

# --------------------------------------------------------------------------- Rotation
DEMO_ROTATION: frozenset[int] = frozenset(
    {
        HAND_OF_GULDAN,
        SHADOW_BOLT,
        DEMONBOLT,
        IMPLOSION,
        CALL_DREADSTALKERS,
        SUMMON_DEMONIC_TYRANT,
        GRIMOIRE_IMP_LORD,
        INFERNAL_BOLT,
        RUINATION,
        POWER_SIPHON,
        DEMONIC_STRENGTH,
        SUMMON_VILEFIEND,
        BILESCOURGE_BOMBERS,
        GUILLOTINE,
        DOOM,
    }
)

DESTRO_ROTATION: frozenset[int] = frozenset(
    {
        INCINERATE,
        CHAOS_BOLT,
        CONFLAGRATE,
        SHADOWBURN,
        WITHER,
        IMMOLATE,
        HAVOC,
        SOUL_FIRE,
        MALEVOLENCE,
        SUMMON_INFERNAL,
        RAIN_OF_FIRE,
        CATACLYSM,
        CHANNEL_DEMONFIRE,
        DIMENSIONAL_RIFT,
    }
)

KNOWN_ROTATION: frozenset[int] = DEMO_ROTATION | DESTRO_ROTATION

# Spec-/Hero-Erkennung aus Casts
DEMO_MARKERS: frozenset[int] = frozenset({HAND_OF_GULDAN, SUMMON_DEMONIC_TYRANT})
DESTRO_MARKERS: frozenset[int] = frozenset({CHAOS_BOLT, WITHER, IMMOLATE})
DIABOLIST_MARKERS: frozenset[int] = frozenset({RUINATION, INFERNAL_BOLT, DIABOLIC_RITUAL})
HELLCALLER_MARKERS: frozenset[int] = frozenset({WITHER, MALEVOLENCE})

# Zauber, die laut Spec als Instants für die Reaktionszeit gelten (zusätzlich zu allen
# Casts mit gemessener Castdauer < 0,5 s, z. B. Demonbolt mit Core).
INSTANT_CANDIDATES: frozenset[int] = frozenset(
    {DEMONBOLT, IMPLOSION, CALL_DREADSTALKERS, CONFLAGRATE, SHADOWBURN, MALEVOLENCE}
)

# Spieler-Buffs, die als "Combat Potion" gelten. Im Referenz-Report wurde kein Kampftrank
# benutzt; IDs werden aus Vergleichslogs ergänzt (siehe analysis/potions).
COMBAT_POTION_BUFFS: frozenset[int] = frozenset()

# Anzeige-Namen (nur Ausgabe, nie Matching)
NAMES: dict[int, str] = {
    HAND_OF_GULDAN: "Hand of Gul'dan",
    SHADOW_BOLT: "Shadow Bolt",
    DEMONBOLT: "Demonbolt",
    IMPLOSION: "Implosion",
    IMPLOSION_DAMAGE: "Implosion",
    ISOLATED_IMPLOSION: "Isolated Implosion",
    CALL_DREADSTALKERS: "Call Dreadstalkers",
    SUMMON_DEMONIC_TYRANT: "Summon Demonic Tyrant",
    GRIMOIRE_IMP_LORD: "Grimoire: Imp Lord",
    INFERNAL_BOLT: "Infernal Bolt",
    RUINATION: "Ruination",
    POWER_SIPHON: "Power Siphon",
    DEMONIC_STRENGTH: "Demonic Strength",
    SUMMON_VILEFIEND: "Summon Vilefiend",
    BILESCOURGE_BOMBERS: "Bilescourge Bombers",
    GUILLOTINE: "Guillotine",
    DOOM: "Doom",
    DIABOLIC_RITUAL: "Diabolic Ritual",
    DOMINION_OF_ARGUS: "Dominion of Argus",
    FEL_FIREBOLT: "Fel Firebolt",
    DEMONIC_CORE_BUFF: "Demonic Core",
    INCINERATE: "Incinerate",
    CHAOS_BOLT: "Chaos Bolt",
    CONFLAGRATE: "Conflagrate",
    SHADOWBURN: "Shadowburn",
    WITHER: "Wither",
    IMMOLATE: "Immolate",
    HAVOC: "Havoc",
    SOUL_FIRE: "Soul Fire",
    MALEVOLENCE: "Malevolence",
    SUMMON_INFERNAL: "Summon Infernal",
    RAIN_OF_FIRE: "Rain of Fire",
    CATACLYSM: "Cataclysm",
    CHANNEL_DEMONFIRE: "Channel Demonfire",
    DIMENSIONAL_RIFT: "Dimensional Rift",
    BLACKENED_SOUL: "Blackened Soul",
    BACKDRAFT_BUFF: "Backdraft",
}


def name(spell_id: int, fallback: dict[int, str] | None = None) -> str:
    """Anzeigename: eigene Tabelle, sonst Name aus dem Report, sonst die ID."""
    if spell_id in NAMES:
        return NAMES[spell_id]
    if fallback and spell_id in fallback and fallback[spell_id]:
        return fallback[spell_id]
    return f"#{spell_id}"
