import os
import re
from abc import ABC, abstractmethod
from logging import Logger
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from poke_env.data import GenData, to_id_str
from poke_env.data.replay_template import REPLAY_TEMPLATE
from poke_env.environment.move import Move
from poke_env.environment.field import Field
from poke_env.environment.pokemon import Pokemon
from poke_env.environment.side_condition import STACKABLE_CONDITIONS, SideCondition
from poke_env.environment.weather import Weather


class SpecialParserCategories:
    # https://bulbapedia.bulbagarden.net/wiki/Category:Moves_that_switch_the_user_out
    MOVES_THAT_SWITCH_THE_USER_OUT = {
        "Baton Pass",
        "Chilly Reception",
        "Flip Turn",
        "Parting Shot",
        "Shed Tail",
        "Teleport",
        "U-turn",
        "Volt Switch",
    }

    # https://bulbapedia.bulbagarden.net/wiki/Category:Moves_that_call_other_moves
    MOVE_OVERRIDE = {
        "Metronome",
        "Me First",
        "Copycat",
        "Nature Power",
        "Magic Coat",
        "Mirror Move",
        "Assist",
        "Snatch",
    }
    MOVE_OVERRIDE_BUT_REVEAL_ANYWAY = {"Sleep Talk"}
    MOVE_IGNORE_ITEMS = {"Custap Berry"}
    CONSECUTIVE_MOVES = {
        "Rollout",
        "Outrage",
        "Thrash",
        "Uproar",
        "Petal Dance",
        "Ice Ball",
    }

    GEN1_PP_ROLLOVERS = {"Bind", "Wrap", "Fire Spin", "Clamp"}

    PLEDGES = {"Grass Pledge", "Water Pledge", "Fire Pledge"}

    # https://bulbapedia.bulbagarden.net/wiki/Category:Moves_that_restore_HP
    RESTORES_PP = {"Lunar Dance"}
    RESTORES_STATUS = {"Healing Wish", "Lunar Dance"}

    ABILITY_STEALS_ABILITY = {"Trace"}

    # https://bulbapedia.bulbagarden.net/wiki/Category:Item-manipulating_moves
    # we are missing some of these; lookout for UnhandledFromMoveItemLogic
    ITEM_APPROVED_SKIP = {"Knock Off", "Recycle", "Fling", "Corrosive Gas"}
    ITEM_UNNAMED_STOLEN = {"Trick", "Switcheroo"}
    ITEM_NAMED_STOLEN = {"Thief", "Covet"}


class AbstractBattle(ABC):
    MESSAGES_TO_IGNORE = {
        "-anim",
        "-block",
        "-burst",
        "-center",
        "-combine",
        "-crit",
        "-fail",
        "-fieldactivate",
        "-hint",
        "-hitcount",
        "-miss",
        "-notarget",
        "-nothing",
        "-ohko",
        "-resisted",
        "-supereffective",
        "-waiting",
        "-zbroken",
        "J",
        "L",
        "askreg",
        "badge",
        "c",
        "chat",
        "crit",
        "debug",
        "deinit",
        "gametype",
        "html",
        "immune",
        "inactiveoff",
        "init",
        "j",
        "join",
        "l",
        "leave",
        "n",
        "name",
        "noinit",
        "rated",
        "rename",
        "resisted",
        "sentchoice",
        "split",
        "supereffective",
        "teampreview",
        "upkeep",
        "uhtml",
        "zbroken",
        "",
    }

    __slots__ = (
        "_anybody_inactive",
        "_available_moves",
        "_available_switches",
        "_battle_tag",
        "_can_dynamax",
        "_can_mega_evolve",
        "_can_tera",
        "_can_z_move",
        "_data",
        "_dynamax_turn",
        "_fields",
        "_finished",
        "_force_switch",
        "_format",
        "_gen",
        "in_team_preview",
        "_last_request",
        "_max_team_size",
        "_maybe_trapped",
        "_move_on_next_request",
        "_opponent_can_dynamax",
        "_opponent_can_mega_evolve",
        "_opponent_can_terrastallize",
        "_opponent_can_z_move",
        "_opponent_dynamax_turn",
        "_opponent_rating",
        "_opponent_side_conditions",
        "_opponent_team",
        "_opponent_username",
        "_player_role",
        "_player_username",
        "_players",
        "_rating",
        "_reconnected",
        "_replay_data",
        "rules",
        "_reviving",
        "_save_replays",
        "_side_conditions",
        "_team_size",
        "_team",
        "_teampreview_team",
        "_teampreview_opponent_team",
        "_teampreview",
        "_trapped",
        "_turn",
        "_wait",
        "_weather",
        "_won",
        "logger",
    )

    def __init__(
        self,
        battle_tag: str,
        username: str,
        logger: Logger,
        save_replays: Union[str, bool],
        gen: int,
    ):
        # Load data
        self._data = GenData.from_gen(gen)

        # Utils attributes
        self._battle_tag: str = battle_tag
        self._gen: int = gen
        self._format: Optional[str] = None
        self._max_team_size: Optional[int] = None
        self._opponent_username: Optional[str] = None
        self._player_role: Optional[str] = None
        self._player_username: str = username
        self._players: List[Dict[str, str]] = []
        self._replay_data: List[List[str]] = []
        self._save_replays: Union[str, bool] = save_replays
        self._team_size: Dict[str, int] = {}
        self._teampreview: bool = False
        self._teampreview_team: Set[Pokemon] = set()
        self._teampreview_opponent_team: Set[Pokemon] = set()
        self._anybody_inactive: bool = False
        self._reconnected: bool = True
        self.logger: Optional[Logger] = logger

        # Turn choice attributes
        self.in_team_preview: bool = False
        self._move_on_next_request: bool = False
        self._wait: Optional[bool] = None

        # Battle state attributes
        self._dynamax_turn: Optional[int] = None
        self._finished: bool = False
        self._last_request: Dict[str, Any] = {}
        self.rules: List[str] = []
        self._turn: int = 0
        self._opponent_can_terrastallize: bool = True
        self._opponent_can_mega_evolve: Union[bool, List[bool]] = True
        self._opponent_can_z_move: Union[bool, List[bool]] = True

        self._opponent_dynamax_turn: Optional[int] = None
        self._opponent_rating: Optional[int] = None
        self._rating: Optional[int] = None
        self._won: Optional[bool] = None

        # In game battle state attributes
        self._weather: Dict[Weather, int] = {}
        self._fields: Dict[Field, int] = {}  # set()
        self._opponent_side_conditions: Dict[SideCondition, int] = {}  # set()
        self._side_conditions: Dict[SideCondition, int] = {}  # set()
        self._reviving: bool = False

        # Pokemon attributes
        self._team: Dict[str, Pokemon] = {}
        self._opponent_team: Dict[str, Pokemon] = {}

    def get_pokemon(
        self,
        identifier: str,
        force_self_team: bool = False,
        details: str = "",
        request: Optional[Dict[str, Any]] = None,
    ) -> Pokemon:
        """Returns the Pokemon object corresponding to given identifier. Can force to
        return object from the player's team if force_self_team is True. If the Pokemon
        object does not exist, it will be created. Details can be given, which is
        necessary to initialize alternate forms (eg. alolan pokemons) properly.

        :param identifier: The identifier to use to retrieve the pokemon.
        :type identifier: str
        :param force_self_team: Wheter to force returning a Pokemon from the player's
            team. Defaults to False.
        :type force_self_team: bool
        :param details: Detailled information about the pokemon. Defaults to ''.
        :type details: str, defaults to ''
        :param request: Detailled information about the pokemon from a request.
            Defaults to None.
        :type request: Dict, optional, defaults to None
        :return: The corresponding pokemon object.
        :rtype: Pokemon
        :raises ValueError: If the team has too many pokemons, as determined by the
            teamsize component of battle initialisation.
        """
        if identifier[3] != " ":
            identifier = identifier[:2] + identifier[3:]

        if identifier in self._team:
            return self._team[identifier]
        elif identifier in self._opponent_team:
            return self._opponent_team[identifier]

        player_role = identifier[:2]
        name = identifier[3:].strip()
        is_mine = player_role == self._player_role

        if is_mine or force_self_team:
            team: Dict[str, Pokemon] = self._team
        else:
            team: Dict[str, Pokemon] = self._opponent_team  # type: ignore

        if self._team_size and len(team) >= self._team_size[player_role]:
            raise ValueError(
                "%s's team already has %d pokemons: cannot add %s to %s"
                % (
                    player_role,
                    self._team_size[player_role],
                    identifier,
                    ", ".join(team.keys()),
                )
            )

        if request:
            team[identifier] = Pokemon(
                request_pokemon=request, name=name, gen=self._data.gen
            )
        elif details:
            team[identifier] = Pokemon(details=details, name=name, gen=self._data.gen)
        else:
            species = identifier[4:]
            team[identifier] = Pokemon(species=species, name=name, gen=self._data.gen)

        return team[identifier]

    @abstractmethod
    def clear_all_boosts(self):
        pass

    def _check_damage_message_for_item(self, split_message: List[str]):
        # Catches when a side takes damage from the opponent's item
        # The item belongs to the side not taking damage
        # Example:
        #   |-damage|p2a: Archeops|88/100|[from] item: Rocky Helmet|[of] p1a: Ferrothorn
        if (
            len(split_message) == 6
            and split_message[4].startswith("[from] item:")
            and split_message[5].startswith("[of]")
        ):
            item = split_message[4].split("item:")[-1]
            pkmn = split_message[5].split("[of]")[-1].strip()
            self.get_pokemon(pkmn).item = to_id_str(item)

        # Catches when a side takes damage from it's own item
        # The item belongs to the same side taking damage
        # Example:
        #   |-damage|p2a: Pikachu|90/100|[from] item: Life Orb
        elif len(split_message) == 5 and split_message[4].startswith("[from] item:"):
            item = split_message[4].split("item:")[-1]
            pkmn = split_message[2]
            self.get_pokemon(pkmn).item = to_id_str(item)

    def _check_damage_message_for_ability(self, split_message: List[str]):
        # Catches when a side takes damage from the opponent's ability
        # the item is from the side not taking damage
        # Example:
        #   |-damage|p2a: Archeops|88/100|[from] ability: Iron Barbs|[of] p1a: Ferrothorn
        if (
            len(split_message) == 6
            and split_message[4].startswith("[from] ability:")
            and split_message[5].startswith("[of]")
        ):
            ability = split_message[4].split("ability:")[-1]
            pkmn = split_message[5].split("[of]")[-1].strip()
            self.get_pokemon(pkmn).ability = to_id_str(ability)

    def _check_heal_message_for_item(self, split_message: List[str]):
        # Catches when a side heals from it's own item
        # the check for item is not None is necessary because the PS simulator will
        #  show the heal message AFTER a berry has already been consumed
        # Examples:
        #  |-heal|p2a: Quagsire|100/100|[from] item: Leftovers
        #  |-heal|p2a: Quagsire|100/100|[from] item: Sitrus Berry
        if len(split_message) == 5 and split_message[4].startswith("[from] item:"):
            pkmn = split_message[2]
            item = split_message[4].split("item:")[-1]
            pkmn_object = self.get_pokemon(pkmn)
            if pkmn_object.item is not None:
                pkmn_object.item = to_id_str(item)

    def _check_heal_message_for_ability(self, split_message: List[str]):
        # Catches when a side heals from it's own ability
        # the "of" component sent by the PS server is a bit misleading
        #   it implies the ability is from the opposite side
        # Example:
        #   |-heal|p2a: Quagsire|100/100|[from] ability: Water Absorb|[of] p1a: Genesect
        #   |-heal|p2b: Excadrill|100/100|from] ability: Hospitality|[of] p2a: Sinistcha
        if len(split_message) == 6 and split_message[4].startswith("[from] ability:"):
            ability = to_id_str(split_message[4].split("ability:")[-1])
            if ability == "hospitality":
                pkmn = split_message[5].replace("[of] ", "").strip()
                self.get_pokemon(pkmn).ability = ability
            else:
                pkmn = split_message[2]
                self.get_pokemon(pkmn).ability = ability

    @abstractmethod
    def end_illusion(self, pokemon_name: str, details: str):
        pass

    def _end_illusion_on(
        self, illusionist: Optional[str], illusioned: Optional[Pokemon], details: str
    ):
        if illusionist is None:
            raise ValueError("Cannot end illusion without an active pokemon.")
        if illusioned is None:
            raise ValueError("Cannot end illusion without an illusioned pokemon.")
        illusionist_mon = self.get_pokemon(illusionist, details=details)

        if illusionist_mon is illusioned:
            return illusionist_mon

        illusionist_mon.switch_in(details=details)
        illusionist_mon.status = (  # type: ignore
            illusioned.status if illusioned.status is not None else None
        )
        illusionist_mon.set_hp(f"{illusioned.current_hp}/{illusioned.max_hp}")

        illusioned.was_illusioned()

        return illusionist_mon

    def _field_end(self, field_str: str):
        field = Field.from_showdown_message(field_str)
        if field is not Field.UNKNOWN:
            self._fields.pop(field)

    def field_start(self, field_str: str):
        field = Field.from_showdown_message(field_str)

        if field.is_terrain:
            self._fields = {
                field: turn
                for field, turn in self._fields.items()
                if not field.is_terrain
            }

        self._fields[field] = self.turn

    def _finish_battle(self):
        if self._save_replays:
            if self._save_replays is True:
                folder = "replays"
            else:
                folder = str(self._save_replays)

            if not os.path.exists(folder):
                os.mkdir(folder)

            with open(
                os.path.join(
                    folder, f"{self._player_username} - {self.battle_tag}.html"
                ),
                "w+",
                encoding="utf-8",
            ) as f:
                formatted_replay = REPLAY_TEMPLATE
                formatted_replay = formatted_replay.replace(
                    "{BATTLE_TAG}", f"{self.battle_tag}"
                )
                formatted_replay = formatted_replay.replace(
                    "{PLAYER_USERNAME}", f"{self._player_username}"
                )
                formatted_replay = formatted_replay.replace(
                    "{OPPONENT_USERNAME}", f"{self._opponent_username}"
                )
                replay_log = f">{self.battle_tag}" + "\n".join(
                    ["|".join(split_message) for split_message in self._replay_data]
                )
                formatted_replay = formatted_replay.replace("{REPLAY_LOG}", replay_log)
                f.write(formatted_replay)

        self._finished = True

    def parse_message(self, split_message: List[str]):
        if self._save_replays:
            self._replay_data.append(split_message)

        event = split_message[:]

        if event[1] in self.MESSAGES_TO_IGNORE:
            return
        elif event[1] == "drag" or event[1] == "switch":
            pokemon, details, hp_status = event[2:5]
            self.switch(pokemon, details, hp_status)
        elif event[1] == "-damage":
            pokemon, hp_status = event[2:4]
            self.get_pokemon(pokemon).damage(hp_status)
            self._check_damage_message_for_item(event)
            self._check_damage_message_for_ability(event)
        elif event[1] == "move":
            # fmt: off
            # JAKE: attempt to modify to match Metamon's version &
            # support unhandled [from]move/ability messages that appear
            # in early gen battles. All changes to `parse_message` are risky.
            # ugly _ variable names mark logic added by metamon's replay parser.

            _poke_str, move = event[2], event[3]
            pokemon = self.get_pokemon(_poke_str)
            reveal_other_move = None
            _extra_from_message = None

            # check if the move failed
            failed = False
            for move_failed_suffix in ["[miss]", "[still]", "[notarget]"]:
                if event[-1] == move_failed_suffix:
                    event = event[:-1]
                    failed = True
            
            # remove all the existing clutter of stripping away extra messages; 
            # there is only one type of message that has any new info to consider.
            for _e in reversed(event):
                if "[from]" in _e:
                    if _e.replace(" ", "") not in {"[from]lockedmove", "[from]Pursuit"}:
                        _extra_from_message = _e
                        break
            
            if _extra_from_message:
                # be overly repetitive by splitting this logic into two clear branches:
                # 1. messages that correctly specify whether they are revealing info about a move or ability
                #    (i.e. "[from]move: Sleep Talk")
                # 2. messages that do *not* specify what type of info they are revealing
                #    (i.e. "[from]Sleep Talk")
                # when I wrote the metamon version I was convinced #2 is from old replay files because
                # #1 is a clear improvement. Now in poke-env on 2025 Showdown, #2 is still present.
                # Must be an early gen difference?
                _extra_from_message.replace("[from] ", "[from]") # cut occasional whitespace
                if "[from]move:" in _extra_from_message or "[from]ability:" in _extra_from_message:
                    _is_move = "[from]move:" in _extra_from_message
                    _is_ability = "[from]ability:" in _extra_from_message
                    if _is_move:
                        _from_move = _extra_from_message.split("[from]move:")[-1].strip()
                        if _from_move in SpecialParserCategories.MOVE_OVERRIDE_BUT_REVEAL_ANYWAY:
                            reveal_other_move = move
                            move = _from_move
                        elif _from_move in SpecialParserCategories.MOVE_OVERRIDE:
                            pass
                        elif _from_move in SpecialParserCategories.PLEDGES:
                            pass
                        elif self.logger is not None:
                            self.logger.warning(
                                "Unmanaged [from]move: message received - move %s in "
                                "cleaned up message %s in battle %s turn %d",
                                _from_move,
                                event,
                                self.battle_tag,
                                self.turn,
                            )
                    elif _is_ability:
                        revealed_ability = _extra_from_message.split("[from]ability:")[-1].strip()
                        pokemon.ability = revealed_ability
                        if revealed_ability not in {"Magic Bounce", "Dancer"} and self.logger is not None:
                            self.logger.warning(
                                "Unmanaged [from]ability: message received - ability %s in "
                                "cleaned up message %s in battle %s turn %d",
                                revealed_ability,
                                event,
                                self.battle_tag,
                                self.turn,
                            )
                else:
                    if self.logger is not None and self._gen > 4:
                        self.logger.warning(
                            "Battle message %s in battle %s turn %d activates ambiguous '[from]move/ability' logic. "
                            "Changes to AbstractBattle.parse_message may be needed if this "
                            "message appears outside of Gen 1-4.",
                            event,
                            self.battle_tag,
                            self.turn,
                        )
                    _ability_or_move = _extra_from_message.split("[from]")[-1].strip()
                    # ths most common reason to hit this branch is partial trapping spam,
                    # i.e. 'p1a Clamp ... [from]Clamp'. In which case Clamp would already be revealed
                    # and there's nothing more to do.
                    _probably_repeat_move = _ability_or_move.lower() == move.lower()
                    _probably_item = _ability_or_move in ({pokemon.item} | SpecialParserCategories.MOVE_IGNORE_ITEMS)
                    if not (_probably_repeat_move or _probably_item):
                        if _ability_or_move in SpecialParserCategories.MOVE_OVERRIDE_BUT_REVEAL_ANYWAY:
                            # i.e. we actually used Sleep Talk, but `move` is another move in the set
                            reveal_other_move = move
                            move = _ability_or_move
                        elif _ability_or_move in SpecialParserCategories.MOVE_OVERRIDE:
                            pass
                        elif _ability_or_move in SpecialParserCategories.PLEDGES:
                            pass
                        elif self.logger is not None:
                            self.logger.warning(
                                "Unmanaged [from] message received - move %s in "
                                "cleaned up message %s in battle %s turn %d",
                                _ability_or_move,
                                event,
                                self.battle_tag,
                                self.turn,
                            )

            # Check if a silent-effect move has occurred (Minimize) and add the effect
            if move.upper().strip() == "MINIMIZE":
                pokemon.start_effect("MINIMIZE")
            
            if reveal_other_move:
                pokemon.moved(reveal_other_move, failed=failed, use=False)
            pokemon.moved(move, failed=failed, use=False)
            # fmt: on
        elif event[1] == "cant":
            pokemon, _ = event[2:4]
            self.get_pokemon(pokemon).cant_move()
        elif event[1] == "turn":
            self.end_turn(int(event[2]))
        elif event[1] == "-heal":
            pokemon, hp_status = event[2:4]
            self.get_pokemon(pokemon).heal(hp_status)
            self._check_heal_message_for_ability(event)
            self._check_heal_message_for_item(event)
        elif event[1] == "-boost":
            pokemon, stat, amount = event[2:5]
            self.get_pokemon(pokemon).boost(stat, int(amount))
        elif event[1] == "-weather":
            weather = event[2]
            if weather == "none":
                self._weather = {}
                return
            else:
                self._weather = {Weather.from_showdown_message(weather): self.turn}
        elif event[1] == "faint":
            pokemon = event[2]
            self.get_pokemon(pokemon).faint()
        elif event[1] == "-unboost":
            pokemon, stat, amount = event[2:5]
            self.get_pokemon(pokemon).boost(stat, -int(amount))
        elif event[1] == "-ability":
            pokemon, cause = event[2:4]
            if len(event) > 4 and event[4].startswith("[from] move:"):
                self.get_pokemon(pokemon).set_temporary_ability(cause)
            else:
                self.get_pokemon(pokemon).ability = cause
        elif split_message[1] == "-start":
            pokemon, effect = event[2:4]
            pokemon = self.get_pokemon(pokemon)  # type: ignore

            if effect == "typechange":
                pokemon.start_effect(effect, details=event[4])  # type: ignore
            else:
                pokemon.start_effect(effect)  # type: ignore

            if pokemon.is_dynamaxed:  # type: ignore
                if pokemon in set(self.team.values()) and self._dynamax_turn is None:
                    self._dynamax_turn = self.turn
                # self._can_dynamax value is set via _parse_request()
                elif (
                    pokemon in set(self.opponent_team.values())
                    and self._opponent_dynamax_turn is None
                ):
                    self._opponent_dynamax_turn = self.turn
                    self.opponent_can_dynamax = False
        elif event[1] == "-activate":
            target, effect = event[2:4]
            if effect.startswith("ability: "):
                ability = effect[9:]
                self.get_pokemon(target).ability = ability
            elif target and effect == "move: Skill Swap":
                self.get_pokemon(target).start_effect(effect, event[4:6])
                actor = event[6].replace("[of] ", "")
                self.get_pokemon(actor).set_temporary_ability(event[5])
            else:
                self.get_pokemon(target).start_effect(effect)
        elif event[1] == "-status":
            pokemon, status = event[2:4]
            self.get_pokemon(pokemon).status = status  # type: ignore
        elif event[1] == "rule":
            self.rules.append(event[2])

        elif event[1] == "-clearallboost":
            self.clear_all_boosts()
        elif event[1] == "-clearboost":
            pokemon = event[2]
            self.get_pokemon(pokemon).clear_boosts()
        elif event[1] == "-clearnegativeboost":
            pokemon = event[2]
            self.get_pokemon(pokemon).clear_negative_boosts()
        elif event[1] == "-clearpositiveboost":
            pokemon = event[2]
            self.get_pokemon(pokemon).clear_positive_boosts()
        elif event[1] == "-copyboost":
            source, target = event[2:4]
            self.get_pokemon(target).copy_boosts(self.get_pokemon(source))
        elif event[1] == "-curestatus":
            pokemon, status = event[2:4]
            self.get_pokemon(pokemon).cure_status(status)
        elif event[1] == "-cureteam":
            pokemon = event[2]
            team = (
                self.team if pokemon[:2] == self._player_role else self._opponent_team
            )
            for mon in team.values():
                mon.cure_status()
        elif event[1] == "-end":
            pokemon, effect = event[2:4]
            self.get_pokemon(pokemon).end_effect(effect)
        elif event[1] == "-endability":
            pokemon = event[2]
            self.get_pokemon(pokemon).set_temporary_ability(None)
        elif event[1] == "-enditem":
            pokemon, item = event[2:4]
            self.get_pokemon(pokemon).end_item(item)
        elif event[1] == "-fieldend":
            condition = event[2]
            self._field_end(condition)
        elif event[1] == "-fieldstart":
            condition = event[2]
            self.field_start(condition)
        elif event[1] in ["-formechange", "detailschange"]:
            pokemon, species = event[2:4]
            self.get_pokemon(pokemon).forme_change(species)
        elif event[1] == "-invertboost":
            pokemon = event[2]
            self.get_pokemon(pokemon).invert_boosts()
        elif event[1] == "-item":
            if len(event) == 6:
                item, cause, pokemon = event[3:6]

                if cause == "[from] ability: Frisk":
                    pokemon = pokemon.split("[of] ")[-1]
                    mon = self.get_pokemon(pokemon)

                    if isinstance(self.active_pokemon, list):
                        self.get_pokemon(event[2]).item = to_id_str(item)
                    else:
                        if mon == self.active_pokemon:
                            self.opponent_active_pokemon.item = to_id_str(item)
                        else:
                            assert mon == self.opponent_active_pokemon
                            self.active_pokemon.item = to_id_str(item)

                    mon.ability = to_id_str("frisk")
                elif cause == "[from] ability: Pickpocket":
                    pickpocket = event[2]
                    pickpocketed = event[5].replace("[of] ", "")
                    item = event[3]

                    self.get_pokemon(pickpocket).item = to_id_str(item)
                    self.get_pokemon(pickpocket).ability = to_id_str("pickpocket")
                    self.get_pokemon(pickpocketed).item = None
                elif cause == "[from] ability: Magician":
                    magician = event[2]
                    victim = event[5].replace("[of] ", "")
                    item = event[3]

                    self.get_pokemon(magician).item = to_id_str(item)
                    self.get_pokemon(magician).ability = to_id_str("magician")
                    self.get_pokemon(victim).item = None
                elif cause in {"[from] move: Thief"}:
                    thief = event[2]
                    victim = event[5].replace("[of] ", "")
                    item = event[3]

                    self.get_pokemon(thief).item = to_id_str(item)
                    self.get_pokemon(victim).item = None
                else:
                    raise ValueError(f"Unhandled item message: {event}")

            else:
                pokemon, item = event[2:4]
                self.get_pokemon(pokemon).item = to_id_str(item)
        elif event[1] == "-mega":
            if self.player_role is not None and not event[2].startswith(
                self.player_role
            ):
                self._opponent_can_mega_evolve = False
            pokemon, megastone = event[2:4]
            self.get_pokemon(pokemon).mega_evolve(megastone)
        elif event[1] == "-mustrecharge":
            pokemon = event[2]
            self.get_pokemon(pokemon).must_recharge = True
        elif event[1] == "-prepare":
            try:
                attacker, move, defender = event[2:5]
                defender_mon = self.get_pokemon(defender)
                if to_id_str(move) == "skydrop":
                    defender_mon.start_effect("Sky Drop")
            except ValueError:
                attacker, move = event[2:4]
                defender_mon = None
            self.get_pokemon(attacker).prepare(move, defender_mon)
        elif event[1] == "-primal":
            pokemon = event[2]
            self.get_pokemon(pokemon).primal()
        elif event[1] == "-setboost":
            pokemon, stat, amount = event[2:5]
            self.get_pokemon(pokemon).set_boost(stat, int(amount))
        elif event[1] == "-sethp":
            pokemon, hp_status = event[2:4]
            self.get_pokemon(pokemon).set_hp(hp_status)
        elif event[1] == "-sideend":
            side, condition = event[2:4]
            self.side_end(side, condition)
        elif event[1] == "-sidestart":
            side, condition = event[2:4]
            self._side_start(side, condition)
        elif event[1] in ["-singleturn", "-singlemove"]:
            pokemon, effect = event[2:4]
            self.get_pokemon(pokemon).start_effect(effect.replace("move: ", ""))
        elif event[1] == "-swapboost":
            source, target, stats = event[2:5]
            source_mon = self.get_pokemon(source)
            target_mon = self.get_pokemon(target)
            if "[from]" in stats:
                if "guardswap" in stats:
                    # JAKE: need to use metamon to check if this still ever triggers
                    all_stats = ["def", "spd"]
                else:
                    all_stats = [
                        "accuracy",
                        "atk",
                        "def",
                        "evasion",
                        "spa",
                        "spd",
                        "spe",
                    ]
                for stat in all_stats:
                    source_mon.boosts[stat], target_mon.boosts[stat] = (
                        target_mon.boosts[stat],
                        source_mon.boosts[stat],
                    )
            else:
                for stat in stats.split(", "):
                    source_mon.boosts[stat], target_mon.boosts[stat] = (
                        target_mon.boosts[stat],
                        source_mon.boosts[stat],
                    )
        elif event[1] == "-transform":
            pokemon, into = event[2:4]
            self.get_pokemon(pokemon).transform(self.get_pokemon(into))
        elif event[1] == "-zpower":
            if self._player_role is not None and not event[2].startswith(
                self._player_role
            ):
                self._opponent_can_z_move = False

            pokemon = event[2]
            self.get_pokemon(pokemon).used_z_move()
        elif event[1] == "clearpoke":
            self.in_team_preview = True
            for mon in self.team.values():
                mon.clear_active()
        elif event[1] == "gen":
            if self._gen != int(event[2]):
                err = f"Battle Initiated with gen {self._gen} but got: {event}"
                raise RuntimeError(err)
        elif event[1] == "tier":
            self._format = re.sub("[^a-z0-9]+", "", event[2].lower())
        elif event[1] == "inactive":
            if "disconnected" in event[2]:
                self._anybody_inactive = True
            elif "reconnected" in event[2]:
                self._anybody_inactive = False
                self._reconnected = True
        elif event[1] == "player":
            if len(event) == 6:
                player, username, avatar, rating = event[2:6]
            elif len(event) == 5:
                player, username, avatar = event[2:5]
                rating = None
            elif len(event) == 4:
                if event[-1] != "":
                    raise RuntimeError(f"Invalid player message: {event}")
                return
            else:
                if not self._anybody_inactive:
                    if self._reconnected:
                        self._reconnected = False
                    else:
                        raise RuntimeError(f"Invalid player message: {event}")
                return
            if username == self._player_username:
                self._player_role = player
            if rating is not None:
                return self._players.append(
                    {
                        "username": username,
                        "player": player,
                        "avatar": avatar,
                        "rating": rating,
                    }
                )
            else:
                return self._players.append(
                    {
                        "username": username,
                        "player": player,
                        "avatar": avatar,
                    }
                )

        elif event[1] == "poke":
            player, details = event[2:4]
            self._register_teampreview_pokemon(player, details)
        elif event[1] == "raw":
            username, rating_info = event[2].split("'s rating: ")
            rating_int = int(rating_info[:4])
            if username == self.player_username:
                self._rating = rating_int
            elif username == self.opponent_username:
                self._opponent_rating = rating_int
            elif self.logger is not None:
                self.logger.warning(
                    "Rating information regarding an unrecognized username received. "
                    "Received '%s', while only known players are '%s' and '%s'",
                    username,
                    self.player_username,
                    self.opponent_username,
                )
        elif event[1] == "replace":
            pokemon = event[2]
            details = event[3]
            self.end_illusion(pokemon, details)
        elif event[1] == "start":
            self.in_team_preview = False
        elif event[1] == "swap":
            pokemon, position = event[2:4]
            self._swap(pokemon, position)  # type: ignore
        elif event[1] == "teamsize":
            player, number = event[2:4]
            self._team_size[player] = int(number)
        elif event[1] in {"message", "-message"}:
            if self.logger is not None:
                self.logger.info("Received message: %s", event[2])
        elif event[1] == "-immune":
            if len(event) == 4:
                mon, cause = event[2:]  # type: ignore

                if cause.startswith("[from] ability:"):
                    cause = cause.replace("[from] ability:", "")
                    self.get_pokemon(mon).ability = to_id_str(cause)  # type: ignore
        elif event[1] == "-swapsideconditions":
            self._side_conditions, self._opponent_side_conditions = (
                self._opponent_side_conditions,
                self._side_conditions,
            )
        elif event[1] == "title":
            player_1, player_2 = event[2].split(" vs. ")
            self.players = player_1, player_2
        elif event[1] == "-terastallize":
            pokemon, type_ = event[2:]
            pokemon = self.get_pokemon(pokemon)  # type: ignore
            pokemon.terastallize(type_)  # type: ignore

            if pokemon.is_terastallized:  # type: ignore
                if pokemon in set(self.opponent_team.values()):
                    self._opponent_can_terrastallize = False
        else:
            raise NotImplementedError(event)

    @abstractmethod
    def parse_request(self, request: Dict[str, Any]):
        pass

    def _register_teampreview_pokemon(self, player: str, details: str):
        if player != self._player_role:
            mon = Pokemon(details=details, gen=self._data.gen)
            self._teampreview_opponent_team.add(mon)

    def side_end(self, side: str, condition_str: str):
        if side[:2] == self._player_role:
            conditions = self.side_conditions
        else:
            conditions = self.opponent_side_conditions
        condition = SideCondition.from_showdown_message(condition_str)
        if condition is not SideCondition.UNKNOWN and condition in conditions:
            conditions.pop(condition)

    def _side_start(self, side: str, condition_str: str):
        if side[:2] == self._player_role:
            conditions = self.side_conditions
        else:
            conditions = self.opponent_side_conditions
        condition = SideCondition.from_showdown_message(condition_str)
        if condition in STACKABLE_CONDITIONS:
            conditions[condition] = conditions.get(condition, 0) + 1
        elif condition not in conditions:
            conditions[condition] = self.turn

    def _swap(self, pokemon_str: str, slot: str):
        if self.logger is not None:
            self.logger.warning("swap method in Battle is not implemented")

    @abstractmethod
    def switch(self, pokemon_str: str, details: str, hp_status: str):
        pass

    def tied(self):
        self._finish_battle()

    def _update_team_from_request(self, side: Dict[str, Any]):
        for pokemon in side["pokemon"]:
            if pokemon["ident"] in self._team:
                self._team[pokemon["ident"]].update_from_request(pokemon)
            else:
                self.get_pokemon(
                    pokemon["ident"], force_self_team=True, request=pokemon
                )

    def won_by(self, player_name: str):
        if player_name == self._player_username:
            self._won = True
        else:
            self._won = False
        self._finish_battle()

    def end_turn(self, turn: int):
        self.turn = turn

        for mon in self.all_active_pokemons:
            if mon:
                mon.end_turn()

    @property
    @abstractmethod
    def active_pokemon(self) -> Any:
        pass

    @property
    @abstractmethod
    def all_active_pokemons(self) -> List[Optional[Pokemon]]:
        pass

    @property
    @abstractmethod
    def available_moves(self) -> Any:
        pass

    @property
    @abstractmethod
    def available_switches(self) -> Any:
        pass

    @property
    def battle_tag(self) -> str:
        """
        :return: The battle identifier.
        :rtype: str
        """
        return self._battle_tag

    @property
    @abstractmethod
    def can_dynamax(self) -> Any:
        pass

    @property
    @abstractmethod
    def can_mega_evolve(self) -> Any:
        pass

    @property
    @abstractmethod
    def can_z_move(self) -> Any:
        pass

    @property
    @abstractmethod
    def can_tera(self) -> Any:
        pass

    @property
    def dynamax_turns_left(self) -> Optional[int]:
        """
        :return: How many turns of dynamax are left. None if dynamax is not active
        :rtype: int, optional
        """
        if self._dynamax_turn is not None and any(
            map(lambda pokemon: pokemon.is_dynamaxed, self._team.values())
        ):
            return max(3 - (self.turn - self._dynamax_turn), 0)
        return None

    @property
    def fields(self) -> Dict[Field, int]:
        """
        :return: A Dict mapping fields to the turn they have been activated.
        :rtype: Dict[Field, int]
        """
        return self._fields

    @property
    def finished(self) -> bool:
        """
        :return: A boolean indicating whether the battle is finished.
        :rtype: Optional[bool]
        """
        return self._finished

    @property
    @abstractmethod
    def force_switch(self) -> Any:
        pass

    @property
    def format(self) -> Optional[str]:
        """
        :return: The format of the battle, in accordance with Showdown protocol
        :rtype: Optional[str]
        """
        return self._format

    @property
    def gen(self) -> int:
        """
        :return: The generation of the battle; will be the parameter with which the
            the battle was initiated
        :rtype: int
        """
        return self._gen

    @property
    def last_request(self) -> Dict[str, Any]:
        """
        The last request received from the server. This allows players to track
            rqid and also maintain parallel battle copies for search/inference

        :return: The last request.
        :rtype: Dict[str, Any]
        """
        return self._last_request

    @property
    def lost(self) -> Optional[bool]:
        """
        :return: If the battle is finished, a boolean indicating whether the battle is
            lost. Otherwise None.
        :rtype: Optional[bool]
        """
        return None if self._won is None else not self._won

    @property
    def max_team_size(self) -> Optional[int]:
        """
        :return: The maximum acceptable size of the team to return in teampreview, if
            applicable.
        :rtype: int, optional
        """
        return self._max_team_size

    @property
    @abstractmethod
    def maybe_trapped(self) -> Any:
        pass

    @property
    @abstractmethod
    def opponent_active_pokemon(self) -> Any:
        pass

    @property
    @abstractmethod
    def opponent_can_dynamax(self) -> Any:
        pass

    @opponent_can_dynamax.setter
    @abstractmethod
    def opponent_can_dynamax(self, value: bool) -> Any:
        pass

    @property
    def opponent_dynamax_turns_left(self) -> Optional[int]:
        """
        :return: How many turns of dynamax are left for the opponent's pokemon.
            None if dynamax is not active
        :rtype: int | None
        """
        if self._opponent_dynamax_turn is not None and any(
            map(lambda pokemon: pokemon.is_dynamaxed, self._opponent_team.values())
        ):
            return max(3 - (self.turn - self._opponent_dynamax_turn), 0)
        return None

    @property
    def opponent_role(self) -> Optional[str]:
        """
        :return: Opponent's role in given battle. p1/p2
        :rtype: str, optional
        """
        if self.player_role == "p1":
            return "p2"
        if self.player_role == "p2":
            return "p1"
        return None

    @property
    def opponent_side_conditions(self) -> Dict[SideCondition, int]:
        """
        :return: The opponent's side conditions. Keys are SideCondition objects, values
            are:

            - the number of layers of the SideCondition if the side condition is
                stackable
            - the turn where the SideCondition was setup otherwise
        :rtype: Dict[SideCondition, int]
        """
        return self._opponent_side_conditions

    @property
    def opponent_team(self) -> Dict[str, Pokemon]:
        """
        During teampreview, keys are not definitive: please rely on values.

        :return: The opponent's team. Keys are identifiers, values are pokemon objects.
        :rtype: Dict[str, Pokemon]
        """
        if self._opponent_team:
            return self._opponent_team
        else:
            return {mon.species: mon for mon in self._teampreview_opponent_team}

    @property
    def opponent_username(self) -> Optional[str]:
        """
        :return: The opponent's username, or None if unknown.
        :rtype: str, optional.
        """
        return self._opponent_username

    @opponent_username.setter
    def opponent_username(self, value: str):
        self._opponent_username = value

    @property
    def player_role(self) -> Optional[str]:
        """
        :return: Player's role in given battle. p1/p2
        :rtype: str, optional
        """
        return self._player_role

    @player_role.setter
    def player_role(self, value: Optional[str]):
        self._player_role = value

    @property
    def player_username(self) -> str:
        """
        :return: The player's username.
        :rtype: str
        """
        return self._player_username

    @player_username.setter
    def player_username(self, value: str):
        self._player_username = value

    @property
    def players(self) -> Tuple[str, str]:
        """
        :return: The pair of players' usernames.
        :rtype: Tuple[str, str]
        """
        return self._players[0]["username"], self._players[1]["username"]

    @players.setter
    def players(self, players: Tuple[str, str]):
        """Sets the battle player's name:

        :param player_1: First player's username.
        :type player_1: str
        :param player_1: Second player's username.
        :type player_2: str
        """
        player_1, player_2 = players
        if player_1 != self._player_username:
            self._opponent_username = player_1
        else:
            self._opponent_username = player_2

    @property
    def rating(self) -> Optional[int]:
        """
        Player's rating after the end of the battle, if it was received.

        :return: The player's rating after the end of the battle.
        :rtype: int, optional
        """
        return self._rating

    @property
    def opponent_rating(self) -> Optional[int]:
        """
        Opponent's rating after the end of the battle, if it was received.

        :return: The opponent's rating after the end of the battle.
        :rtype: int, optional
        """
        return self._opponent_rating

    @property
    def side_conditions(self) -> Dict[SideCondition, int]:
        """
        :return: The player's side conditions. Keys are SideCondition objects, values
            are:

            - the number of layers of the side condition if the side condition is
                stackable
            - the turn where the SideCondition was setup otherwise
        :rtype: Dict[SideCondition, int]
        """
        return self._side_conditions

    @property
    def team(self) -> Dict[str, Pokemon]:
        """
        :return: The player's team. Keys are identifiers, values are pokemon objects.
        :rtype: Dict[str, Pokemon]
        """
        return self._team

    @team.setter
    def team(self, value: Dict[str, Pokemon]):
        self._team = value

    @property
    def team_size(self) -> int:
        """
        :return: The number of Pokemon in the player's team.
        :rtype: int
        """
        if self._player_role is not None:
            return self._team_size[self._player_role]
        raise ValueError(
            "Team size cannot be inferred without an assigned player role."
        )

    @property
    def teampreview(self) -> bool:
        """
        :return: Wheter the battle is awaiting a teampreview order.
        :rtype: bool
        """
        return self._teampreview

    @property
    def teampreview_team(self) -> Set[Pokemon]:
        """
        :return: The player's team during teampreview.
        :rtype: Set[Pokemon]
        """
        return self._teampreview_team

    @teampreview_team.setter
    def teampreview_team(self, value: Set[Pokemon]):
        self._teampreview_team = value

    @property
    def teampreview_opponent_team(self) -> Set[Pokemon]:
        """
        :return: The opponent's team during teampreview.
        :rtype: Set[Pokemon]
        """
        return self._teampreview_opponent_team

    @property
    @abstractmethod
    def trapped(self) -> Any:
        pass

    @trapped.setter
    @abstractmethod
    def trapped(self, value: Any):
        pass

    @property
    def turn(self) -> int:
        """
        :return: The current battle turn.
        :rtype: int
        """
        return self._turn

    @turn.setter
    def turn(self, turn: int):
        """Sets the current turn counter to given value.

        :param turn: Current turn value.
        :type turn: int
        """
        self._turn = turn

    @property
    def weather(self) -> Dict[Weather, int]:
        """
        :return: A Dict mapping the battle's weather (if any) to its starting turn
        :rtype: Dict[Weather, int]
        """
        return self._weather

    @property
    def won(self) -> Optional[bool]:
        """
        :return: If the battle is finished, a boolean indicating whether the battle is
            won. Otherwise None.
        :rtype: Optional[bool]
        """
        return self._won

    @property
    def move_on_next_request(self) -> bool:
        """
        :return: Wheter the next received request should yield a move order directly.
            This can happen when a switch is forced, or an error is encountered.
        :rtype: bool
        """
        return self._move_on_next_request

    @move_on_next_request.setter
    def move_on_next_request(self, value: bool):
        self._move_on_next_request = value

    @property
    def reviving(self) -> bool:
        return self._reviving
