--!strict
--[[
	RoundAndWaveDirector
	Server-authoritative game mode loop & wave defense director:
	`Lobby` -> `Intermission` -> `MapVote` -> `ActiveRound` -> `Victory` / `Defeat` -> `Reset`
]]

export type RoundPhase = "Lobby" | "Intermission" | "MapVote" | "ActiveRound" | "Victory" | "Defeat"

export type WaveSpec = {
	waveNumber: number,
	enemyCount: number,
	enemyHealthMultiplier: number,
	rewardCoins: number,
}

export type DirectorState = {
	phase: RoundPhase,
	currentWave: number,
	maxWaves: number,
	enemiesRemaining: number,
	selectedMap: string,
	mapVotes: { [string]: number },
	roundNumber: number,
}

local RoundAndWaveDirector = {}

function RoundAndWaveDirector.CreateDirector(maxWaves: number?, defaultMap: string?): DirectorState
	return {
		phase = "Lobby",
		currentWave = 0,
		maxWaves = maxWaves or 5,
		enemiesRemaining = 0,
		selectedMap = defaultMap or "AlpineCitadel",
		mapVotes = {},
		roundNumber = 0,
	}
end

function RoundAndWaveDirector.CastMapVote(state: DirectorState, mapId: string, weight: number?): number
	local w = math.max(1, math.floor(weight or 1))
	state.mapVotes[mapId] = (state.mapVotes[mapId] or 0) + w
	return state.mapVotes[mapId]
end

function RoundAndWaveDirector.ResolveWinningMap(state: DirectorState, fallbackMap: string?): string
	local bestMap = fallbackMap or state.selectedMap
	local bestScore = -1
	for mapId, votes in pairs(state.mapVotes) do
		if votes > bestScore or (votes == bestScore and mapId < bestMap) then
			bestScore = votes
			bestMap = mapId
		end
	end
	state.selectedMap = bestMap
	return bestMap
end

function RoundAndWaveDirector.ComputeWaveSpec(waveNumber: number): WaveSpec
	local w = math.max(1, math.floor(waveNumber))
	return {
		waveNumber = w,
		enemyCount = 4 + w * 3,
		enemyHealthMultiplier = tonumber(string.format("%.2f", 1.0 + (w - 1) * 0.25)) or 1.0,
		rewardCoins = 50 + w * 35,
	}
end

function RoundAndWaveDirector.StartNextWave(state: DirectorState): (boolean, WaveSpec?, RoundPhase)
	if state.currentWave >= state.maxWaves then
		state.phase = "Victory"
		state.enemiesRemaining = 0
		return false, nil, state.phase
	end
	if state.currentWave == 0 then
		state.roundNumber += 1
	end
	state.currentWave += 1
	state.phase = "ActiveRound"
	local spec = RoundAndWaveDirector.ComputeWaveSpec(state.currentWave)
	state.enemiesRemaining = spec.enemyCount
	return true, spec, state.phase
end

function RoundAndWaveDirector.RecordEnemyDefeated(state: DirectorState, count: number?): (number, boolean, RoundPhase)
	local defeated = math.max(1, math.floor(count or 1))
	state.enemiesRemaining = math.max(0, state.enemiesRemaining - defeated)
	if state.enemiesRemaining == 0 and state.phase == "ActiveRound" then
		if state.currentWave >= state.maxWaves then
			state.phase = "Victory"
		end
		return 0, true, state.phase
	end
	return state.enemiesRemaining, false, state.phase
end

function RoundAndWaveDirector.ResetToLobby(state: DirectorState): RoundPhase
	state.phase = "Lobby"
	state.currentWave = 0
	state.enemiesRemaining = 0
	table.clear(state.mapVotes)
	return state.phase
end

return RoundAndWaveDirector
