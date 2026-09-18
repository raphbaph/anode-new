/**
 * Weighted Instant Runoff Voting engine.
 * Browser + Node. No DOM. Deterministic given a seed.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.IRV = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const OPTION_KEYS = "ABCDE";

  const ROLE_ARCHETYPES = [
    { name: "Security circle", lean: { safety: 2.1, core: 0.9, delay: 0.8, growth: -0.5 } },
    { name: "Whale delegate", lean: { growth: 1.3, token: 1.5, core: 0.4, public: -0.2 } },
    { name: "Core steward", lean: { core: 1.9, safety: 0.8, ops: 0.5 } },
    { name: "Grant reviewer", lean: { public: 1.7, ecosystem: 1.4, growth: 0.4 } },
    { name: "Newcomer bloc", lean: { public: 1.3, growth: 0.9, core: -0.2 } },
    { name: "Treasury council", lean: { ops: 1.6, safety: 0.7, token: 0.5, growth: -0.3 } },
    { name: "Protocol guild", lean: { core: 1.5, throughput: 1.4, safety: 0.4 } },
    { name: "Community mod", lean: { public: 1.4, ecosystem: 1.1, delay: 0.3 } },
    { name: "Research desk", lean: { delay: 1.3, safety: 1.0, public: 0.5 } },
    { name: "Liquidity guild", lean: { growth: 1.6, token: 1.2, throughput: 0.7 } },
    { name: "Working-group lead", lean: { ops: 1.3, ecosystem: 0.9, core: 0.4 } },
    { name: "Builder cohort", lean: { throughput: 1.5, core: 1.0, growth: 0.6 } },
    { name: "Ops steward", lean: { ops: 1.8, safety: 0.4, delay: 0.2 } },
    { name: "Forum regular", lean: { public: 1.1, delay: 0.8, ecosystem: 0.6 } },
    { name: "Audit firm", lean: { safety: 2.0, delay: 1.1, core: 0.3, growth: -0.7 } },
  ];

  const SCENARIOS = [
    {
      id: "treasury",
      kind: "DAO treasury",
      title: "How should the DAO allocate next quarter’s 2.4M treasury budget?",
      context:
        "Runway is 28 months. Four working groups submitted competing spend plans. Tokenholders want a single allocation, not a split that funds everything thinly.",
      options: [
        { id: "core", name: "Core protocol maintenance", blurb: "Keep existing systems solvent and staffed.", tags: ["core", "safety", "ops"] },
        { id: "grants", name: "Ecosystem grants", blurb: "Fund builders outside the core team.", tags: ["ecosystem", "public", "growth"] },
        { id: "liquidity", name: "Liquidity incentives", blurb: "Deepen markets for the native token.", tags: ["growth", "token"] },
        { id: "runway", name: "Operations runway", blurb: "Extend payroll, vendors, and legal cover.", tags: ["ops", "safety"] },
        { id: "buyback", name: "Token buyback", blurb: "Retire float and signal scarcity.", tags: ["token", "growth"] },
      ],
    },
    {
      id: "grants",
      kind: "Grant round",
      title: "Which track should receive the largest share of the public-goods round?",
      context:
        "The matching pool is fixed. Reviewers asked for one primary track so the round has a readable thesis instead of five underfunded categories.",
      options: [
        { id: "tooling", name: "Developer tooling", blurb: "SDKs, indexers, and local-testing kits.", tags: ["core", "throughput"] },
        { id: "education", name: "Education & onboarding", blurb: "Docs, courses, and first-hour UX.", tags: ["public", "ecosystem"] },
        { id: "research", name: "Research & security", blurb: "Audits, formal methods, bug bounties.", tags: ["safety", "delay", "core"] },
        { id: "community", name: "Local community hubs", blurb: "Meetups, translations, regional ops.", tags: ["public", "ecosystem"] },
        { id: "bridges", name: "Cross-chain infrastructure", blurb: "Bridges, messaging, shared liquidity.", tags: ["throughput", "growth"] },
      ],
    },
    {
      id: "upgrade",
      kind: "Protocol upgrade",
      title: "Which upgrade path should the protocol take this cycle?",
      context:
        "A hard fork window opens in nine weeks. Engineering can deliver one primary path well, or several poorly. The vote is a commitment, not a poll.",
      options: [
        { id: "patch", name: "Conservative security patch", blurb: "Ship fixes only; defer new surface area.", tags: ["safety", "core", "delay"] },
        { id: "fees", name: "Fee-market rewrite", blurb: "Modularize fees before touching consensus.", tags: ["core", "throughput"] },
        { id: "privacy", name: "Privacy-preserving default", blurb: "Shielded transfers on by default.", tags: ["safety", "public"] },
        { id: "scale", name: "Aggressive throughput scaling", blurb: "Raise block capacity and parallelize execution.", tags: ["throughput", "growth"] },
        { id: "audit", name: "Delay and commission an audit", blurb: "Pause the fork until an outside review lands.", tags: ["delay", "safety"] },
      ],
    },
    {
      id: "mandate",
      kind: "Working group mandate",
      title: "What mandate should the new coordination working group receive?",
      context:
        "Delegates approved the group’s existence, not its scope. A fuzzy mandate will recreate the forum thread it was meant to replace.",
      options: [
        { id: "rights", name: "Decision-rights mapping", blurb: "Write down who may decide what, and when.", tags: ["core", "ops"] },
        { id: "pay", name: "Contributor compensation redesign", blurb: "Replace ad-hoc bounties with a durable pay system.", tags: ["ops", "public"] },
        { id: "pipeline", name: "Forum-to-vote pipeline", blurb: "Shorten the path from proposal to ballot.", tags: ["throughput", "ops"] },
        { id: "delegates", name: "Delegation quality review", blurb: "Audit inactive and over-concentrated delegates.", tags: ["safety", "public"] },
        { id: "sunset", name: "90-day audit, then sunset", blurb: "Diagnose, publish, and dissolve the group.", tags: ["delay", "safety"] },
      ],
    },
    {
      id: "incident",
      kind: "Incident response",
      title: "After the oracle incident, which response should the DAO fund first?",
      context:
        "Losses were contained. Trust was not. The next spend is a signal about whether the network treats this as an accident or a design failure.",
      options: [
        { id: "bounty", name: "Expand the bug bounty", blurb: "Pay researchers to find the next failure first.", tags: ["safety", "public"] },
        { id: "insurance", name: "Capitalize an insurance pool", blurb: "Backstop users for a defined class of faults.", tags: ["safety", "ops", "token"] },
        { id: "pause", name: "Protocol pause and staged restart", blurb: "Halt, patch, and resume with checkpoints.", tags: ["safety", "delay", "core"] },
        { id: "postmortem", name: "Independent postmortem", blurb: "Fund an outside reconstruction of the failure.", tags: ["delay", "public", "safety"] },
        { id: "migrate", name: "Migration grants", blurb: "Help affected users and apps move to safer rails.", tags: ["public", "ecosystem", "growth"] },
      ],
    },
    {
      id: "unlock",
      kind: "Token policy",
      title: "How should unlocked ecosystem tokens be handled?",
      context:
        "A cliff unlock hits in 40 days. Doing nothing dumps float onto thin markets. Every option reallocates future influence, not just supply.",
      options: [
        { id: "extend", name: "Extend the lock with higher rewards", blurb: "Pay holders to keep tokens illiquid.", tags: ["token", "delay", "growth"] },
        { id: "linear", name: "Linear unlock to contributors", blurb: "Release to people still doing the work.", tags: ["public", "ops"] },
        { id: "stream", name: "Redirect to a public-goods stream", blurb: "Route unlocks into ongoing grants.", tags: ["public", "ecosystem"] },
        { id: "burn", name: "Burn a portion, rest to treasury", blurb: "Reduce supply and restock operations.", tags: ["token", "ops"] },
        { id: "retro", name: "Snapshot a retroactive round", blurb: "Allocate to demonstrated past work.", tags: ["public", "ecosystem", "delay"] },
      ],
    },
  ];

  function createRng(seed) {
    let t = seed >>> 0;
    return function rng() {
      t += 0x6d2b79f5;
      let r = Math.imul(t ^ (t >>> 15), 1 | t);
      r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }

  function parseSeed(value) {
    if (value == null || value === "") return null;
    if (typeof value === "number" && Number.isFinite(value)) return value >>> 0;
    const text = String(value).trim();
    if (/^\d+$/.test(text)) return Number(text) >>> 0;
    if (/^[0-9a-fA-F]{1,8}$/.test(text)) return parseInt(text, 16) >>> 0;
    let h = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function formatSeed(seed) {
    return (seed >>> 0).toString(16).padStart(8, "0");
  }

  function shuffle(list, rng) {
    const next = list.slice();
    for (let i = next.length - 1; i > 0; i -= 1) {
      const j = Math.floor(rng() * (i + 1));
      const tmp = next[i];
      next[i] = next[j];
      next[j] = tmp;
    }
    return next;
  }

  function pickScenario(rng, lastId) {
    const pool = lastId ? SCENARIOS.filter((scenario) => scenario.id !== lastId) : SCENARIOS;
    return pool[Math.floor(rng() * pool.length)];
  }

  function optionKey(index) {
    return OPTION_KEYS[index] || String(index + 1);
  }

  function scoreOption(option, lean, noise) {
    return option.tags.reduce((sum, tag) => sum + (lean[tag] || 0), 0) + noise;
  }

  function skewedPowers(rng, count) {
    const raw = Array.from({ length: count }, (_, index) => {
      const heavy = index < 2 ? 9 + rng() * 16 : 2 + rng() * 7;
      return Math.pow(heavy, 1.12);
    });
    const shuffled = shuffle(raw, rng);
    const total = shuffled.reduce((sum, value) => sum + value, 0);
    let powers = shuffled.map((value) => Math.max(1, Math.round((value / total) * 100)));
    const cap = 24;
    function sum() {
      return powers.reduce((acc, value) => acc + value, 0);
    }
    function heaviestIndex() {
      let index = 0;
      for (let i = 1; i < powers.length; i += 1) {
        if (powers[i] > powers[index]) index = i;
      }
      return index;
    }
    while (powers[heaviestIndex()] > cap) {
      const index = heaviestIndex();
      powers[index] -= 1;
      const light = powers.indexOf(Math.min.apply(null, powers));
      powers[light] += 1;
    }
    const drift = 100 - sum();
    if (drift !== 0) {
      const light = powers.indexOf(Math.min.apply(null, powers));
      powers[light] += drift;
      if (powers[light] < 1) powers[light] = 1;
    }
    return powers;
  }

  function generateElectorate(rng, scenario) {
    const voterCount = 8 + Math.floor(rng() * 5);
    const roles = shuffle(ROLE_ARCHETYPES, rng).slice(0, voterCount);
    const powers = skewedPowers(rng, voterCount);
    const options = scenario.options;

    return roles.map((role, index) => {
      const ranked = options
        .map((option) => ({
          id: option.id,
          score: scoreOption(option, role.lean, (rng() - 0.45) * 1.15),
        }))
        .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));

      return {
        id: "v" + index,
        name: role.name,
        power: powers[index],
        ranking: ranked.map((entry) => entry.id),
      };
    });
  }

  function currentChoice(ranking, remainingSet) {
    for (let i = 0; i < ranking.length; i += 1) {
      if (remainingSet.has(ranking[i])) return ranking[i];
    }
    return null;
  }

  function tallyRound(voters, remainingIds) {
    const remainingSet = remainingIds instanceof Set ? remainingIds : new Set(remainingIds);
    const tallies = {};
    remainingSet.forEach((id) => {
      tallies[id] = 0;
    });
    let continuing = 0;
    let exhausted = 0;
    const holders = {};
    remainingSet.forEach((id) => {
      holders[id] = [];
    });

    voters.forEach((voter) => {
      const choice = currentChoice(voter.ranking, remainingSet);
      if (choice) {
        tallies[choice] += voter.power;
        continuing += voter.power;
        holders[choice].push(voter.id);
      } else {
        exhausted += voter.power;
      }
    });

    return { tallies, continuing, exhausted, holders };
  }

  function hasMajority(tallies, continuing) {
    if (continuing <= 0) return null;
    const ids = Object.keys(tallies);
    for (let i = 0; i < ids.length; i += 1) {
      if (tallies[ids[i]] * 2 > continuing) return ids[i];
    }
    return null;
  }

  function pickEliminated(tallies, remaining, optionOrder) {
    let min = Infinity;
    const tied = [];
    remaining.forEach((id) => {
      const votes = tallies[id] || 0;
      if (votes < min) {
        min = votes;
        tied.length = 0;
        tied.push(id);
      } else if (votes === min) {
        tied.push(id);
      }
    });
    if (tied.length === 1) return tied[0];
    let latest = -1;
    let chosen = tied[0];
    tied.forEach((id) => {
      const index = optionOrder.indexOf(id);
      if (index > latest) {
        latest = index;
        chosen = id;
      }
    });
    return chosen;
  }

  function transferMap(voters, remaining, eliminated) {
    const remainingSet = new Set(remaining);
    const nextSet = new Set(remaining.filter((id) => id !== eliminated));
    const flows = {};
    nextSet.forEach((id) => {
      flows[id] = 0;
    });
    let exhausted = 0;
    const movers = [];

    voters.forEach((voter) => {
      if (currentChoice(voter.ranking, remainingSet) !== eliminated) return;
      const next = currentChoice(voter.ranking, nextSet);
      movers.push(voter.id);
      if (next) flows[next] += voter.power;
      else exhausted += voter.power;
    });

    return { flows, exhausted, movers };
  }

  function computeRunoff(options, voters) {
    const optionOrder = options.map((option) => option.id);
    const remaining = optionOrder.slice();
    const totalPower = voters.reduce((sum, voter) => sum + voter.power, 0);
    const rounds = [];

    while (remaining.length > 0) {
      const snapshot = tallyRound(voters, remaining);
      const majorityId =
        remaining.length === 1 ? remaining[0] : hasMajority(snapshot.tallies, snapshot.continuing);
      const round = {
        index: rounds.length + 1,
        remaining: remaining.slice(),
        tallies: Object.assign({}, snapshot.tallies),
        holders: snapshot.holders,
        continuing: snapshot.continuing,
        exhausted: snapshot.exhausted,
        totalPower,
        threshold: snapshot.continuing / 2,
        majorityId: majorityId,
        eliminated: null,
        transfers: null,
      };

      if (majorityId) {
        rounds.push(round);
        break;
      }

      const eliminated = pickEliminated(snapshot.tallies, remaining, optionOrder);
      round.eliminated = eliminated;
      round.transfers = transferMap(voters, remaining, eliminated);
      rounds.push(round);
      remaining.splice(remaining.indexOf(eliminated), 1);
    }

    const finalRound = rounds[rounds.length - 1];
    const winnerId = finalRound ? finalRound.majorityId : null;
    return {
      rounds,
      winnerId,
      totalPower,
      recap: buildRecap(options, rounds, winnerId),
    };
  }

  function optionName(options, id) {
    const found = options.find((option) => option.id === id);
    return found ? found.name : id;
  }

  function buildRecap(options, rounds, winnerId) {
    if (!winnerId || !rounds.length) {
      return { winnerId: null, summary: "No winner.", eliminated: [], exhausted: 0 };
    }
    const finalRound = rounds[rounds.length - 1];
    const eliminated = rounds.filter((round) => round.eliminated).map((round) => round.eliminated);
    const votes = finalRound.tallies[winnerId] || 0;
    const share = finalRound.continuing ? Math.round((votes / finalRound.continuing) * 100) : 0;
    const lastStanding = finalRound.remaining.length === 1 && votes * 2 <= finalRound.continuing;
    const summary = lastStanding
      ? optionName(options, winnerId) +
        " is the last remaining option after " +
        eliminated.length +
        " elimination" +
        (eliminated.length === 1 ? "" : "s") +
        ", holding " +
        votes +
        " of " +
        finalRound.continuing +
        " continuing voting power."
      : optionName(options, winnerId) +
        " crossed a majority in round " +
        finalRound.index +
        ", holding " +
        votes +
        " of " +
        finalRound.continuing +
        " continuing voting power (" +
        share +
        "%)." +
        (eliminated.length
          ? " " +
            eliminated.length +
            " option" +
            (eliminated.length === 1 ? " was" : "s were") +
            " eliminated first."
          : " It won on first preferences.");
    return {
      winnerId,
      summary,
      eliminated,
      exhausted: finalRound.exhausted,
      votes,
      continuing: finalRound.continuing,
      share,
      rounds: rounds.length,
    };
  }

  function roundExplainer(options, round, isFinal) {
    if (isFinal && round.majorityId) {
      const lastStanding = round.remaining.length === 1 && round.tallies[round.majorityId] * 2 <= round.continuing;
      if (lastStanding) {
        return (
          "Last option standing — " +
          optionName(options, round.majorityId) +
          " remains after every other choice was eliminated."
        );
      }
      return (
        "Majority reached — " +
        optionName(options, round.majorityId) +
        " holds more than half of the continuing voting power."
      );
    }
    if (round.eliminated) {
      const moved = Object.keys(round.transfers.flows).reduce((sum, id) => sum + round.transfers.flows[id], 0);
      const exhausted = round.transfers.exhausted;
      let text =
        "No majority. Last-place " +
        optionName(options, round.eliminated) +
        " is eliminated; " +
        moved +
        " voting power transfers to remaining choices.";
      if (exhausted) text += " " + exhausted + " power is exhausted.";
      return text;
    }
    return "Counting first preferences among the options still in the race.";
  }

  function simulate(seed) {
    const parsed = parseSeed(seed);
    const resolvedSeed = parsed == null ? 1 : parsed;
    const rng = createRng(resolvedSeed);
    const scenario = pickScenario(rng);
    const voters = generateElectorate(rng, scenario);
    const runoff = computeRunoff(scenario.options, voters);
    return {
      seed: resolvedSeed,
      seedLabel: formatSeed(resolvedSeed),
      scenario,
      voters,
      runoff,
    };
  }

  function timingFor(rounds, reducedMotion) {
    const elimCount = rounds.filter((round) => round.eliminated).length;
    const readSlots = Math.max(1, rounds.length);
    if (reducedMotion) {
      return {
        compose: 180,
        ballots: 180,
        read: 420,
        flash: 0,
        transfer: 0,
        reveal: 240,
      };
    }
    const target = 28000;
    const compose = 1400;
    const ballots = 1800;
    const flash = elimCount ? 1100 : 0;
    const transfer = elimCount ? 2100 : 0;
    const leftover = target - compose - ballots - elimCount * (flash + transfer);
    const read = leftover / (readSlots + 0.55);
    const reveal = read * 0.55;
    return { compose, ballots, read, flash, transfer, reveal };
  }

  return {
    SCENARIOS,
    ROLE_ARCHETYPES,
    OPTION_KEYS,
    createRng,
    parseSeed,
    formatSeed,
    shuffle,
    pickScenario,
    optionKey,
    generateElectorate,
    tallyRound,
    hasMajority,
    pickEliminated,
    computeRunoff,
    simulate,
    timingFor,
    roundExplainer,
    currentChoice,
  };
});
