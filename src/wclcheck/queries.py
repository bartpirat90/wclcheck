"""Alle GraphQL-Queries gegen die WCL Client-API v2 an einem Ort."""

RATE_LIMIT_FRAGMENT = """
rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
"""

# Report-Kopf: Zone, Encounter-Fights (Kills und Wipes), Actors inkl. Pet-Zuordnung.
REPORT = """
query Report($code: String!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      region { slug }
      zone { id name }
      fights(killType: Encounters) {
        id
        encounterID
        name
        kill
        difficulty
        startTime
        endTime
        averageItemLevel
        size
        inProgress
        friendlyPlayers
      }
      masterData {
        actors { id name type subType petOwner server }
      }
    }
  }
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
}
"""

# Fähigkeiten des Reports: gameID ↔ Name (nur zur Ermittlung der Spell-IDs, nie zum Matchen).
REPORT_ABILITIES = """
query ReportAbilities($code: String!) {
  reportData {
    report(code: $code) {
      masterData {
        abilities { gameID name type icon }
      }
    }
  }
}
"""

# Events mit Paginierung über nextPageTimestamp. `dataType` steuert Casts / DamageDone /
# Buffs / Resources / CombatantInfo / Summons / Deaths.
EVENTS = """
query Events(
  $code: String!, $fightIDs: [Int]!, $startTime: Float!, $endTime: Float!,
  $dataType: EventDataType, $sourceID: Int, $targetID: Int, $abilityID: Float,
  $hostilityType: HostilityType, $includeResources: Boolean, $limit: Int
) {
  reportData {
    report(code: $code) {
      events(
        fightIDs: $fightIDs, startTime: $startTime, endTime: $endTime,
        dataType: $dataType, sourceID: $sourceID, targetID: $targetID,
        abilityID: $abilityID, hostilityType: $hostilityType,
        includeResources: $includeResources, limit: $limit
      ) {
        data
        nextPageTimestamp
      }
    }
  }
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
}
"""

# Tabellen (Summary → combatantInfo/Gear; DamageDone viewBy Ability als günstige Alternative).
TABLE = """
query Table(
  $code: String!, $fightIDs: [Int]!, $startTime: Float!, $endTime: Float!,
  $dataType: TableDataType, $sourceID: Int, $targetID: Int, $viewBy: ViewType,
  $hostilityType: HostilityType
) {
  reportData {
    report(code: $code) {
      table(
        fightIDs: $fightIDs, startTime: $startTime, endTime: $endTime,
        dataType: $dataType, sourceID: $sourceID, targetID: $targetID,
        viewBy: $viewBy, hostilityType: $hostilityType
      )
    }
  }
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
}
"""

# Rankings pro Encounter/Spec/Schwierigkeit (JSON-Blob mit rankings[]).
CHARACTER_RANKINGS = """
query Rankings(
  $encounterID: Int!, $className: String, $specName: String, $difficulty: Int,
  $page: Int, $serverRegion: String, $metric: CharacterRankingMetricType
) {
  worldData {
    encounter(id: $encounterID) {
      id
      name
      characterRankings(
        className: $className, specName: $specName, difficulty: $difficulty,
        page: $page, serverRegion: $serverRegion, metric: $metric,
        includeCombatantInfo: false
      )
    }
  }
  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }
}
"""

# Parse-Perzentil eines Spielers im eigenen Report (rankings-JSON pro Fight).
REPORT_RANKINGS = """
query ReportRankings($code: String!, $fightIDs: [Int], $playerMetric: ReportRankingMetricType) {
  reportData {
    report(code: $code) {
      rankings(fightIDs: $fightIDs, playerMetric: $playerMetric)
    }
  }
}
"""
