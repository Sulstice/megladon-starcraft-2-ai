#!/usr/bin/env python3
#
# Megladon Base Class
#
# --------------------

# Main Modules
# ------------
import sc2
import reload
import random
import cv2
import numpy as np
import time
import os

# SC2 Submodules
# ----------------------
from sc2.player import Bot, Computer
from sc2 import Race, Difficulty, Result


# SC2 Building Constants
# ----------------------
from sc2.constants import *

# SC2 File training data
# ----------------------
os.environ["SC2PATH"] = '/Applications/StarCraft II/'
HEADLESS = False


class Megladon(sc2.BotAI):

    __version__ = '0.0.1'
    __slots__ = []

    def __init__(self):
        sc2.BotAI.__init__(self)
        self.ITERATIONS_PER_MINUTE = 165
        self.MAX_WORKERS = 80
        self.proxy_built = False
        self.warpgate_started = False
        self.researched_warpgate = False
        self.iteration = 0
        self.max_worker_count = 70
        self.do_something_after = 0
        self.train_data = []
        self.flipped = 0

    def on_end(self, game_result):

        print('--- on_end called ---')
        print(game_result)

        if str(game_result) == 'Result.Victory':
            np.save("{}.npy".format(str(int(time.time()))), np.array(self.train_data))

    # On step will be the base function of what occurs at every event
    async def on_step(self, iteration):

        """

        What to handle with each iteration

        """
        self.iteration = iteration
        if iteration == 0:
            await self.chat_send("glhf")

        # We might have multiple bases, so distribute workers between them (not every game step)
        if self.iteration % 10 == 0:
            await self.distribute_workers()

        # # If game time is greater than 2 min, make sure to always scout with one worker
        # if self.time > 120:
        #     await self.scout()

        # what we plan to do at each step
        await self.distribute_workers()
        await self.chronoboost_nexus()
        await self.scout()
        await self.build_workers()
        await self.gather_minerals()
        await self.gather_vespene_gas()
        await self.build_pylons()
        await self.build_assimilators()
        await self.build_twilight_council()
        await self.research_twilight_research(ability='blink')
        await self.research_warpgate()
        await self.expand()
        await self.build_gateway_and_cybernetic_core()
        await self.build_stalkers()
        await self.intel()
        await self.attack_with_stalkers()

    def _find_target(self, state):

        """

        Used to find arbitrary targets depending on whether we see enemy buildings or enemey units.

        """
        if len(self.known_enemy_units) > 0:
            return random.choice(self.known_enemy_units)
        elif len(self.known_enemy_structures) > 0:
            return random.choice(self.known_enemy_structures)
        else:
            return self.enemy_start_locations[0]

    def get_rally_location(self):

        """

        Rally the troops to the nearest location.

        Returns:
            rally_location (Object): Closest pylon to the center.


        """
        rally_location = self.units(PYLON).ready.closest_to(self.game_info.map_center).position
        return rally_location

    def get_game_center_random(self, offset_x=50, offset_y=50):
        x = self.game_info.map_center.x
        y = self.game_info.map_center.y

        rand = random.random()
        if rand < 0.2:
            x += offset_x
        elif rand < 0.4:
            x -= offset_x
        elif rand < 0.6:
            y += offset_y
        elif rand < 0.8:
            y -= offset_y

        return sc2.position.Point2((x,y))

    def _random_location_variance(self, enemy_start_location):

        """

        Retrieve random locations around the enemies base to keep constant vision

        """
        x = enemy_start_location[0]
        y = enemy_start_location[1]

        x += ((random.randrange(-20, 20))/100) * enemy_start_location[0]
        y += ((random.randrange(-20, 20))/100) * enemy_start_location[1]

        if x < 0:
            x = 0
        if y < 0:
            y = 0
        if x > self.game_info.map_size[0]:
            x = self.game_info.map_size[0]
        if y > self.game_info.map_size[1]:
            y = self.game_info.map_size[1]

        go_to = sc2.position.Point2(sc2.position.Pointlike((x,y)))
        return go_to

    def get_base_build_location(self, base, min_distance=10, max_distance=20):

        """

        Retrieve the base build location of the home base

        Arguments:
            base (SC2 Object): First base nexus of the home base
            min_distance (int): minimum distance away to build the building (so we don't build in the mineral line)
            max_distance (int): maximum distance away to build the building (hopefully so it doesn't scout)

        Return:
            position (SC2 Object): The base position of the nexus.

        """
        return base.position.towards(self.get_game_center_random(), random.randrange(min_distance, max_distance))


    async def chronoboost_nexus(self):

        """

        Chronoboost nexus's that are availiable.

        Characterisitics:
            - Chronoboost the first available nexus.

        """

        for nexus in self.units(NEXUS):
            if nexus.energy >= 50:
                abilities = await self.get_available_abilities(nexus)
                if AbilityId.EFFECT_CHRONOBOOSTENERGYCOST in abilities:

                    if self.units(CYBERNETICSCORE).ready.exists:
                        cybernetics_core = self.units(CYBERNETICSCORE).ready.first
                        if not cybernetics_core.has_buff(BuffId.CHRONOBOOSTENERGYCOST):
                            await self.do(nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, cybernetics_core))

                    # Next, prioritize CB on gates
                    for gateway in (self.units(GATEWAY).ready | self.units(WARPGATE).ready):
                        if not gateway.has_buff(BuffId.CHRONOBOOSTENERGYCOST):
                            await self.do(nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, gateway))
                            return # Don't CB anything else this step

                    # Otherwise CB nexus
                    if not nexus.has_buff(BuffId.CHRONOBOOSTENERGYCOST):
                        await self.do(nexus(AbilityId.EFFECT_CHRONOBOOSTENERGYCOST, nexus))

    async def build_workers(self):

        """

        Constantly build workers and worker economy.

        Characteristics of the workers:

            - Max 80 workers
            - Never stop building unless attacked or rushing.

        """

        nexus = self.units(NEXUS).ready.random

        if self.workers.amount < self.units(NEXUS).amount * 15 and nexus.is_idle:
            if self.can_afford(PROBE):
                await self.do(nexus.train(PROBE))

                for nexus in self.units(NEXUS).ready:
                    # Train workers until at nexus max (+4)
                    if self.workers.amount < self.max_worker_count and nexus.noqueue and nexus.assigned_harvesters < nexus.ideal_harvesters + 2 :
                        if self.can_afford(PROBE) and self.supply_used < 198:
                            await self.do(nexus.train(PROBE))

            # Idle workers near nexus should always be mining (we want to allow idle workers near cannons in enemy base)
            if self.workers.idle.closer_than(50, nexus).exists:
                worker = self.workers.idle.closer_than(50, nexus).first
                await self.do(worker.gather(self.state.mineral_field.closest_to(nexus)))

            # Worker defense: If enemy unit is near nexus, attack with a nearby workers
            nearby_enemies = self.known_enemy_units.not_structure.filter(lambda unit: not unit.is_flying).closer_than(30, nexus).prefer_close_to(nexus)
            if nearby_enemies.amount >= 1 and nearby_enemies.amount <= 10 and self.workers.exists:

                # We have nearby enemies, so attack them with a worker
                workers = self.workers.sorted_by_distance_to(nearby_enemies.first).take(nearby_enemies.amount * 2, False)

                for worker in workers:
                    #if not self.has_order(ATTACK, worker):
                    await self.do(worker.attack(nearby_enemies.closer_than(30, nexus).closest_to(worker)))

            else:
                # No nearby enemies, so make sure to return all workers to base
                for worker in self.workers.closer_than(50, nexus):
                    if len(worker.orders) == 1 and worker.orders[0].ability.id in [ATTACK]:
                        await self.do(worker.gather(self.state.mineral_field.closest_to(nexus)))

    async def gather_minerals(self):

        """

        Gather minerals for any idle worker.

        Characteristics:

            - Any idle probe allocate towards a mineral field.


        """

        for nexus in self.units(NEXUS).ready:
            for worker in self.workers.closer_than(50, nexus):
                if len(worker.orders) == 1 and worker.orders[0].ability.id in [ATTACK]:
                    await self.do(worker.gather(self.state.mineral_field.closest_to(nexus)))

    async def gather_vespene_gas(self):


        """

        Gather Vespene Gas


        Characteristics:

            - Any idle workers and gather any vespene gas

        """

        for assimlator in self.units(ASSIMILATOR):
            if assimlator.assigned_harvesters < assimlator.ideal_harvesters:
                worker = self.workers.closer_than(20, assimlator)
                if worker.exists:
                    await self.do(worker.random.gather(assimlator))

    async def build_pylons(self):

        """

        Build Pylons

        Characteristics of the pylons:

            - Build near nexus, mineral lines, and walls.
            - Always keep ahead of supply by 10.

        """

        nexus = self.units(NEXUS).ready.random

        if self.supply_left < 5 and not self.already_pending(PYLON):
            if self.can_afford(PYLON):
                await self.build(PYLON, near=nexus.position.towards(self.game_info.map_center, 5))
            return


    async def build_assimilators(self):

        """

        Build vespene gas and adjust based on what different type of builds we are applying. For now full saturation.

        Characterisitcs:

            - Always allocate probes to the gas and adjust as such.

        """
        for nexus in self.units(NEXUS).ready:

            vespene_geysers = self.state.vespene_geyser.closer_than(20.0, nexus)

            for vespene_geyser in vespene_geysers:
                if not self.can_afford(ASSIMILATOR):
                    break

                worker = self.select_build_worker(vespene_geyser.position)
                if worker is None:
                    break

                if not self.units(ASSIMILATOR).closer_than(1.0, vespene_geyser).exists:
                    await self.do(worker.build(ASSIMILATOR, vespene_geyser))


    async def expand(self):

        """

        Expand the nexus under full saturation of mineral lines and if you can afford. For now if the game exceeds a
        certain time marker we can head into MACRO (expansions change)

        Characteristics:

            - Early to Mid Game keep expansions set towards under 3
            - Macro game adjust the expansion with variation of attacks.

        """
        if self.units(NEXUS).amount < 4 and not self.already_pending(NEXUS):
            if self.can_afford(NEXUS):
                await self.expand_now()

    async def build_gateway_and_cybernetic_core(self):

        """

        Build Initial Gateway and Cybernetics Core facility

        Characteristics:

            - Build one gateway and one cybernetics core, may vary depending on build.

        """
        if self.units(PYLON).ready.exists:
            pylon = self.units(PYLON).ready.random

            if self.units(GATEWAY).ready.exists and not self.units(CYBERNETICSCORE):
                if self.can_afford(CYBERNETICSCORE) and not self.already_pending(CYBERNETICSCORE):
                    await self.build(CYBERNETICSCORE, near=pylon)

            elif len(self.units(GATEWAY)) < ((self.iteration / self.ITERATIONS_PER_MINUTE)/2):
                if self.can_afford(GATEWAY) and not self.already_pending(GATEWAY):
                    await self.build(GATEWAY, near=pylon)

            if self.units(CYBERNETICSCORE).ready.exists:
                if len(self.units(ROBOTICSFACILITY)) < 1:
                    if self.can_afford(ROBOTICSFACILITY) and not self.already_pending(ROBOTICSFACILITY):
                        await self.build(ROBOTICSFACILITY, near=pylon)


    async def build_stalkers(self):

        """

        Build the stalkers (my favourite unit)

        Characteristics:

            - Build a stalker anytime a gateway is available

        """

        # Train at Gateways
        for gateway in self.units(GATEWAY).ready:
            abilities = await self.get_available_abilities(gateway)
            if gateway:
                if MORPH_WARPGATE in abilities:
                    await self.do(gateway(MORPH_WARPGATE))
                    return
                elif self.supply_used < 198 and self.supply_left >= 2:
                    if self.can_afford(STALKER):
                        await self.do(gateway.train(STALKER))

        # Warp-in from Warpgates
        for warpgate in self.units(WARPGATE).ready:
            abilities = await self.get_available_abilities(warpgate)
            if AbilityId.WARPGATETRAIN_STALKER in abilities and self.supply_used < 198 and self.supply_left >= 2:
                if self.can_afford(STALKER):
                    self.do(warpgate.warp_in(STALKER, self.get_rally_location()))

    async def attack_with_stalkers(self):

        """

        If any stalkers are around we need to bounce between defense and offense.

        Characterisitics:

            - Attack the enemy if we see the enemy.
            - If we have 12 stalkers then lets attack the enemy

        """

        # Defaults
        if len(self.units(STALKER).idle) > 0:
            choice = random.randrange(0, 4)
            target = False
            if self.iteration > self.do_something_after:
                if choice == 0:
                    # no attack
                    wait = random.randrange(20, 165)
                    self.do_something_after = self.iteration + wait

                elif choice == 1:
                    #attack_unit_closest_nexus
                    if len(self.known_enemy_units) > 0:
                        target = self.known_enemy_units.closest_to(random.choice(self.units(NEXUS)))

                elif choice == 2:
                    #attack enemy structures
                    if len(self.known_enemy_structures) > 0:
                        target = random.choice(self.known_enemy_structures)

                elif choice == 3:
                    #attack_enemy_start
                    target = self.enemy_start_locations[0]

                if target:
                    for vr in self.units(STALKER).idle:
                        await self.do(vr.attack(target))
                y = np.zeros(4)
                y[choice] = 1
                print(y)
                self.train_data.append([y,self.flipped])

    async def research_warpgate(self):

        """

        Research the warpgate uupgrade for warping in stalkers.

        """

        if self.units(CYBERNETICSCORE).ready.exists and self.can_afford(RESEARCH_WARPGATE) and not self.warpgate_started:
            cybernetics_core = self.units(CYBERNETICSCORE).ready.first
            # await self.do(cybernetics_core(RESEARCH_WARPGATE))
            self.warpgate_started = True


    async def build_protoss_natural_wall(self):

        """

        Build the protoss wall

        """

        if self.units(CYBERNETICSCORE).amount >= 1 and not self.proxy_built and self.can_afford(PYLON):
            p = self.game_info.map_center.towards(self.main_base_ramp, 20)
            await self.build(PYLON, near=p)
            self.proxy_built = True

    async def build_twilight_council(self):

        """

        Build the Twilight Council

        Characteristics

            - Research Blink

        """

        # Build Twilight Council (requires Cybernetics Core)
        if not self.units(TWILIGHTCOUNCIL).exists and not self.already_pending(TWILIGHTCOUNCIL):
            if self.can_afford(TWILIGHTCOUNCIL) and self.units(CYBERNETICSCORE).ready.exists:
                await self.build(TWILIGHTCOUNCIL, near=self.get_base_build_location(self.units(NEXUS).first))
            return

    async def research_twilight_research(self, ability):

        """

        Research the twilight count

        Arguments:
            ability (String): whether you want to research charge or blink

        """

        if not self.units(TWILIGHTCOUNCIL).ready.exists:
            return
        twilight = self.units(TWILIGHTCOUNCIL).first

        # Research Blink and Charge at Twilight
        # Temporary bug workaround: Don't go further unless we can afford blink
        if not self.can_afford(RESEARCH_BLINK):
            return
        #
        # if twilight.is_idle:
        #     abilities = await self.get_available_abilities(twilight)
        #     if ability == 'blink':
        #         if RESEARCH_BLINK in abilities:
        #             if self.can_afford(RESEARCH_BLINK):
        #                 await self.do(twilight(RESEARCH_BLINK))
        #             return
        #     elif ability == 'charge':
        #         if RESEARCH_CHARGE in abilities:
        #             if self.can_afford(RESEARCH_CHARGE):
        #                 await self.do(twilight(RESEARCH_CHARGE))
        #             return
        #

    async def scout(self):

        """

        Scout using the observer

        """
        if len(self.units(OBSERVER)) > 0:
            scout = self.units(OBSERVER)[0]
            if scout.is_idle:
                enemy_location = self.enemy_start_locations[0]
                move_to = self._random_location_variance(enemy_location)
                await self.do(scout.move(move_to))

        else:
            for rf in self.units(ROBOTICSFACILITY).ready.noqueue:
                if self.can_afford(OBSERVER) and self.supply_left > 0:
                    await self.do(rf.train(OBSERVER))

    async def intel(self):

        """

        Get intel about the game data to feed into the neural network

        """

        draw_dict = {
            NEXUS: [15, (0, 255, 0)],
            PYLON: [3, (20, 235, 0)],
            PROBE: [1, (55, 200, 0)],
            ASSIMILATOR: [2, (55, 200, 0)],
            GATEWAY: [3, (200, 100, 0)],
            CYBERNETICSCORE: [3, (150, 150, 0)],
            STALKER: [5, (255, 0, 0)],
            ROBOTICSFACILITY: [5, (215, 155, 0)],
            OBSERVER: [2, (255, 0, 0)]
        }

        # flip around. It's y, x when you're dealing with an array.
        game_data = np.zeros((self.game_info.map_size[1], self.game_info.map_size[0], 3), np.uint8)

        for unit_type in draw_dict:
            for unit in self.units(unit_type):
                pos = unit.position
                cv2.circle(game_data, (int(pos[0]), int(pos[1])), draw_dict[unit_type][0], draw_dict[unit_type][1], -1)

        main_base_names = ["nexus", "commandcenter", "hatchery"]
        for enemy_building in self.known_enemy_structures:
            pos = enemy_building.position
            if enemy_building.name.lower() not in main_base_names:
                cv2.circle(game_data, (int(pos[0]), int(pos[1])), 5, (200, 50, 212), -1)

        for enemy_building in self.known_enemy_structures:
            pos = enemy_building.position
            if enemy_building.name.lower() in main_base_names:
                cv2.circle(game_data, (int(pos[0]), int(pos[1])), 15, (0, 0, 255), -1)

        line_max = 50
        mineral_ratio = self.minerals / 1500
        if mineral_ratio > 1.0:
            mineral_ratio = 1.0

        vespene_ratio = self.vespene / 1500

        if vespene_ratio > 1.0:
            vespene_ratio = 1.0

        population_ratio = self.supply_left / self.supply_cap
        if population_ratio > 1.0:
            population_ratio = 1.0

        plausible_supply = self.supply_cap / 200.0

        military_weight = len(self.units(STALKER)) / (self.supply_cap - self.supply_left)
        if military_weight > 1.0:
            military_weight = 1.0


        cv2.line(game_data, (0, 19), (int(line_max*military_weight), 19), (250, 250, 200), 3)  # worker/supply ratio
        cv2.line(game_data, (0, 15), (int(line_max*plausible_supply), 15), (220, 200, 200), 3)  # plausible supply (supply/200.0)
        cv2.line(game_data, (0, 11), (int(line_max*population_ratio), 11), (150, 150, 150), 3)  # population ratio (supply_left/supply)
        cv2.line(game_data, (0, 7), (int(line_max*vespene_ratio), 7), (210, 200, 0), 3)  # gas / 1500
        cv2.line(game_data, (0, 3), (int(line_max*mineral_ratio), 3), (0, 255, 25), 3)  # minerals minerals/1500

        self.flipped = cv2.flip(game_data, 0)

        if not HEADLESS:
            resized = cv2.resize(self.flipped, dsize=None, fx=2, fy=2)
            cv2.imshow('Intel', resized)
            cv2.waitKey(1)



def main():

    player_config = [
        Bot(Race.Protoss, Megladon()),
        Computer(Race.Terran, Difficulty.Easy)
    ]

    genenis = sc2.main._host_game_iter(
        sc2.maps.get("AcropolisLE"),
        player_config,
        realtime=False
    )

    while True:
        r = next(genenis)
        genenis.send(player_config)

if __name__ == '__main__':

    main()