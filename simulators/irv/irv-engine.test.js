const IRV = require("./irv-engine.js");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL:", message);
    process.exitCode = 1;
  } else {
    console.log("ok ", message);
  }
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    console.error("FAIL:", message, "expected", expected, "got", actual);
    process.exitCode = 1;
  } else {
    console.log("ok ", message);
  }
}

(function classicIRV() {
  const options = [{ id: "A", name: "A" }, { id: "B", name: "B" }, { id: "C", name: "C" }];
  const voters = [
    { id: "a", power: 42, ranking: ["A", "B", "C"] },
    { id: "b", power: 26, ranking: ["B", "C", "A"] },
    { id: "c", power: 32, ranking: ["C", "B", "A"] },
  ];
  const result = IRV.computeRunoff(options, voters);
  assertEqual(result.rounds.length, 2, "classic IRV has two rounds");
  assertEqual(result.rounds[0].tallies.A, 42, "round 1 A");
  assertEqual(result.rounds[0].tallies.B, 26, "round 1 B");
  assertEqual(result.rounds[0].tallies.C, 32, "round 1 C");
  assertEqual(result.rounds[0].eliminated, "B", "lowest first preference is eliminated");
  assertEqual(result.rounds[0].transfers.flows.C, 26, "B's power transfers to C");
  assertEqual(result.winnerId, "C", "C wins after transfer");
  assertEqual(result.rounds[1].tallies.C, 58, "C has 58 in the final round");
  assertEqual(result.rounds[1].tallies.A, 42, "A remains at 42");
})();

(function weightedTransfer() {
  const options = [{ id: "A" }, { id: "B" }, { id: "C" }, { id: "D" }];
  const voters = [
    { id: "1", power: 18, ranking: ["A", "C", "B", "D"] },
    { id: "2", power: 14, ranking: ["B", "C", "A", "D"] },
    { id: "3", power: 11, ranking: ["C", "A", "B", "D"] },
    { id: "4", power: 9, ranking: ["D", "C", "B", "A"] },
    { id: "5", power: 8, ranking: ["A", "B", "C", "D"] },
    { id: "6", power: 7, ranking: ["B", "A", "C", "D"] },
    { id: "7", power: 6, ranking: ["C", "B", "A", "D"] },
    { id: "8", power: 4, ranking: ["D", "A", "C", "B"] },
  ];
  const result = IRV.computeRunoff(options, voters);
  const first = result.rounds[0];
  assertEqual(first.tallies.A, 26, "A first preferences 18+8");
  assertEqual(first.tallies.B, 21, "B first preferences 14+7");
  assertEqual(first.tallies.C, 17, "C first preferences 11+6");
  assertEqual(first.tallies.D, 13, "D first preferences 9+4");
  assertEqual(first.eliminated, "D", "D eliminated first");
  assertEqual(first.transfers.flows.C, 9, "9 vp from D moves to C");
  assertEqual(first.transfers.flows.A, 4, "4 vp from D moves to A");
  const second = result.rounds[1];
  assertEqual(second.tallies.A, 30, "A after D transfers");
  assertEqual(second.tallies.C, 26, "C after D transfers");
  assert(result.winnerId, "a winner is declared");
  assert(second.continuing === 77, "continuing power stays 77");
})();

(function exhaustedBallotsChangeDenominator() {
  const options = [{ id: "A" }, { id: "B" }, { id: "C" }];
  const voters = [
    { id: "1", power: 10, ranking: ["A", "B", "C"] },
    { id: "2", power: 9, ranking: ["B", "A", "C"] },
    { id: "3", power: 6, ranking: ["C"] },
  ];
  const result = IRV.computeRunoff(options, voters);
  assertEqual(result.rounds[0].eliminated, "C", "C last in round 1");
  assertEqual(result.rounds[0].transfers.exhausted, 6, "C's power is exhausted");
  const final = result.rounds[result.rounds.length - 1];
  assertEqual(final.exhausted, 6, "final exhausted is 6");
  assertEqual(final.continuing, 19, "majority uses continuing power");
  assertEqual(result.winnerId, "A", "A has 10 of 19, a majority of continuing");
  assert(final.tallies.A * 2 > final.continuing, "A strictly exceeds half of continuing");
})();

(function lastRemainingWithoutOriginalMajority() {
  const options = [{ id: "A" }, { id: "B" }, { id: "C" }];
  const voters = [
    { id: "1", power: 5, ranking: ["A"] },
    { id: "2", power: 5, ranking: ["B"] },
    { id: "3", power: 4, ranking: ["C"] },
  ];
  const result = IRV.computeRunoff(options, voters);
  assertEqual(result.rounds[0].eliminated, "C", "C out first");
  assertEqual(result.rounds[1].continuing, 10, "C's 4 power is exhausted");
  assertEqual(result.rounds[1].eliminated, "B", "A and B tie at 5; later-listed B is eliminated");
  assertEqual(result.winnerId, "A", "A wins as last remaining");
  assertEqual(result.rounds[2].remaining.length, 1, "final round has one option");
  assert(result.rounds[2].tallies.A * 2 <= result.rounds[2].totalPower, "winner never held a majority of original power");
})();

(function firstRoundMajority() {
  const options = [{ id: "A" }, { id: "B" }, { id: "C" }];
  const voters = [
    { id: "1", power: 12, ranking: ["A", "B", "C"] },
    { id: "2", power: 5, ranking: ["B", "C", "A"] },
    { id: "3", power: 4, ranking: ["C", "B", "A"] },
  ];
  const result = IRV.computeRunoff(options, voters);
  assertEqual(result.rounds.length, 1, "majority in round 1");
  assertEqual(result.winnerId, "A", "A wins immediately");
  assertEqual(result.rounds[0].eliminated, null, "no elimination");
})();

(function tieBreaksTowardLaterListed() {
  const options = [{ id: "A" }, { id: "B" }, { id: "C" }];
  const voters = [
    { id: "1", power: 8, ranking: ["A", "B", "C"] },
    { id: "2", power: 4, ranking: ["B", "A", "C"] },
    { id: "3", power: 4, ranking: ["C", "A", "B"] },
  ];
  const result = IRV.computeRunoff(options, voters);
  assertEqual(result.rounds[0].tallies.B, 4, "B tied for last");
  assertEqual(result.rounds[0].tallies.C, 4, "C tied for last");
  assertEqual(result.rounds[0].eliminated, "C", "later-listed option is eliminated on a last-place tie");
})();

(function seededReplayIsStable() {
  const first = IRV.simulate(0xa11ce);
  const second = IRV.simulate(0xa11ce);
  assertEqual(first.scenario.id, second.scenario.id, "same seed, same scenario");
  assertEqual(first.voters.length, second.voters.length, "same seed, same voter count");
  assertEqual(JSON.stringify(first.voters), JSON.stringify(second.voters), "same seed, same ballots");
  assertEqual(first.runoff.winnerId, second.runoff.winnerId, "same seed, same winner");
})();

(function generatedRacesAreWellFormed() {
  for (let i = 0; i < 40; i += 1) {
    const model = IRV.simulate(1000 + i * 97);
    const optionIds = model.scenario.options.map(function (option) {
      return option.id;
    });
    assert(model.scenario.options.length >= 4 && model.scenario.options.length <= 5, "4–5 options");
    assert(model.voters.length >= 8 && model.voters.length <= 12, "8–12 voters");
    const power = model.voters.reduce(function (sum, voter) {
      return sum + voter.power;
    }, 0);
    assert(power > 0, "positive total power");
    model.voters.forEach(function (voter) {
      assert(voter.power >= 1, voter.name + " has power");
      assertEqual(voter.ranking.length, optionIds.length, voter.name + " ranks every option");
      assertEqual(new Set(voter.ranking).size, optionIds.length, voter.name + " has unique ranks");
    });
    assert(model.runoff.winnerId, "every generated race names a winner");
    const maxShare = Math.max.apply(
      null,
      model.voters.map(function (voter) {
        return voter.power / power;
      })
    );
    assert(maxShare <= 0.4, "no single voter holds 40%+");
  }
})();

(function parseSeedHex() {
  assertEqual(IRV.parseSeed("00a11ce"), 0xa11ce, "hex seed parses");
  assertEqual(IRV.formatSeed(0xa11ce), "000a11ce", "seed formats to 8 hex chars");
})();

(function timingHitsWindow() {
  for (let i = 0; i < 30; i += 1) {
    const model = IRV.simulate(i * 13 + 9);
    const t = IRV.timingFor(model.runoff.rounds, false);
    const elim = model.runoff.rounds.filter(function (round) {
      return round.eliminated;
    }).length;
    const total = t.compose + t.ballots + elim * (t.flash + t.transfer) + model.runoff.rounds.length * t.read + t.reveal;
    assert(total > 27000 && total < 29000, "runoff timing near 28s (" + Math.round(total) + "ms)");
  }
})();

if (process.exitCode) {
  console.error("IRV engine tests failed.");
} else {
  console.log("All IRV engine tests passed.");
}
