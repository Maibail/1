# -*- coding: utf-8 -*-
from .QuModLibs.Server import *
import time

SHIP_STATE_KEY = "ship_state"
SHIP_STATE_SAILING = "sailing"
SHIP_STATE_DOCKED = "docked"

shipState = {}         # entityId -> sailing|docked
assemblingLocks = set()  # 同一艘船互斥锁
operationCooldowns = {}  # entityId -> nextAllowedTs


def _notify_player(playerId, text):
    comp = serverApi.GetEngineCompFactory().CreateGame(playerId)
    comp.SetNotifyMsg(text, serverApi.GenerateColor("BLUE"))


def _get_ship_state(entityId, defaultState=SHIP_STATE_DOCKED):
    if entityId in shipState:
        return shipState[entityId]
    exComp = serverApi.GetEngineCompFactory().CreateExtraData(entityId)
    state = exComp.GetExtraData(SHIP_STATE_KEY) or defaultState
    shipState[entityId] = state
    return state


def _set_ship_state(entityId, state):
    shipState[entityId] = state
    exComp = serverApi.GetEngineCompFactory().CreateExtraData(entityId)
    exComp.SetExtraData(SHIP_STATE_KEY, state, True)


def _lock_ship(entityId):
    if entityId in assemblingLocks:
        return False
    assemblingLocks.add(entityId)
    return True


def _unlock_ship(entityId):
    assemblingLocks.discard(entityId)


def _is_in_cooldown(entityId):
    return time.time() < operationCooldowns.get(entityId, 0)


def _mark_cooldown(entityId, cooldown=0.5):
    operationCooldowns[entityId] = time.time() + cooldown


@AllowCall
@InjectRPCPlayerId
def RequestRestoreShip(playerId, shipEntityId, restoreSuccess=True):
    """停船RPC: 仅sailing态允许执行，成功后切换docked并KillEntity。"""
    if not _lock_ship(shipEntityId):
        _notify_player(playerId, "当前不可操作（冷却/状态不符）")
        return False

    try:
        if _is_in_cooldown(shipEntityId):
            _notify_player(playerId, "当前不可操作（冷却/状态不符）")
            return False

        currentState = _get_ship_state(shipEntityId, SHIP_STATE_SAILING)
        if currentState != SHIP_STATE_SAILING:
            _notify_player(playerId, "已停泊")
            return False

        if not restoreSuccess:
            _notify_player(playerId, "当前不可操作（冷却/状态不符）")
            return False

        _set_ship_state(shipEntityId, SHIP_STATE_DOCKED)
        gameComp = serverApi.GetEngineCompFactory().CreateGame(levelId)
        gameComp.KillEntity(shipEntityId)
        _mark_cooldown(shipEntityId)
        _notify_player(playerId, "已停泊")
        return True
    finally:
        _unlock_ship(shipEntityId)


@AllowCall
@InjectRPCPlayerId
def AssembleShip(playerId, shipEntityId):
    """组装入口: 仅docked态允许重新组装，成功后切换sailing。"""
    if not _lock_ship(shipEntityId):
        _notify_player(playerId, "当前不可操作（冷却/状态不符）")
        return False

    try:
        if _is_in_cooldown(shipEntityId):
            _notify_player(playerId, "当前不可操作（冷却/状态不符）")
            return False

        currentState = _get_ship_state(shipEntityId, SHIP_STATE_DOCKED)
        if currentState != SHIP_STATE_DOCKED:
            _notify_player(playerId, "已起航")
            return False

        _set_ship_state(shipEntityId, SHIP_STATE_SAILING)
        _mark_cooldown(shipEntityId)
        _notify_player(playerId, "已起航")
        return True
    finally:
        _unlock_ship(shipEntityId)


@Listen("ServerBlockUseEvent")
def OnBlockUse(args={}):
    """方块交互入口: 舵方块仅在停泊态时允许触发组装。"""
    if args.get("blockName") != "rudder":
        return

    playerId = args.get("playerId")
    shipEntityId = args.get("entityId")
    if not playerId or not shipEntityId:
        return

    if _get_ship_state(shipEntityId, SHIP_STATE_DOCKED) != SHIP_STATE_DOCKED:
        _notify_player(playerId, "当前不可操作（冷却/状态不符）")
        return

    AssembleShip(playerId, shipEntityId)
