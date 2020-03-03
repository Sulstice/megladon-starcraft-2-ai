#!/usr/bin/env python3
#
# Megladon Base Class
#
# --------------------

# Main Modules
# ------------
import sc2

# SC2 Submodules
# ----------------------
from sc2.player import Bot, Computer
from sc2 import run_game, maps, Race, Difficulty

# SC2 Building Constants
# ----------------------
from sc2.constants import NEXUS, PYLON, ASSIMILATOR

# SC2 Unit Constants
# ----------------------
from sc2.constants import PROBE

class Megladon(sc2.BotAI):

    __version__ = '0.0.1'
    __slots__ = []

    # On step will be the base function of what occurs at every event
    async def on_step(self, iteration):

        # what we plan to do at each step
        await self.distribute_workers()
        await self.build_workers()
        await self.build_pylons()
        await self.expand()
        await self.build_assimilator()

    async def build_workers(self):

        """

        Constantly build workers and worker economy.

        Characteristics of the workers:

            - Max 80 workers
            - Never stop building unless attacked or rushing.

        """
        for nexus in self.units(NEXUS).ready.noqueue:
            if self.can_afford(PROBE):
                await self.do(nexus.train(PROBE))

    async def build_pylons(self):

        """

        Build Pylons

        Characteristics of the pylons:

            - Build near nexus, mineral lines, and walls.
            - Always keep ahead of supply by 10.

        """
        if self.supply_left < 10 and not self.already_pending(PYLON):
            nexuses = self.units(NEXUS).ready
            if nexuses.exists:
                if self.can_afford(PYLON):
                    await self.build(PYLON, near=nexuses.first)

    async def expand(self):

        """

        Expand the nexus under full saturation of mineral lines and if you can afford. For now if the game exceeds a
        certain time marker we can head into MACRO (expansions change)

        Characteristics:

            - Early to Mid Game keep expansions set towards under 3
            - Macro game adjust the expansion with variation of attacks.

        """
        if self.units(NEXUS).amount < 3 and self.can_afford(NEXUS):
            await self.expand_now()

    async def build_assimilator(self):

        """

        Build vespene gas and adjust based on what different type of builds we are applying. For now full saturation.

        Characterisitcs:

            - Always allocate probes to the gas and adjust as such.

        """
        for nexus in self.units(NEXUS).ready:
            vaspenes = self.state.vespene_geyser.closer_than(25.0, nexus)
            for vaspene in vaspenes:
                if not self.can_afford(ASSIMILATOR):
                    break
                worker = self.select_build_worker(vaspene.position)
                if worker is None:
                    break
                if not self.units(ASSIMILATOR).closer_than(1.0, vaspene).exists:
                    await self.do(worker.build(ASSIMILATOR, vaspene))


if __name__ == '__main__':

    run_game(maps.get("DiscoBloodbathLE"), [
        Bot(Race.Protoss, Megladon()),
        Computer(Race.Terran, Difficulty.Easy)
    ], realtime=True)