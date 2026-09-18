(function () {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.querySelector("[data-irv]");
  if (!root || !window.IRV) return;

  const els = {
    generate: Array.prototype.slice.call(document.querySelectorAll("[data-irv-generate]")),
    kind: root.querySelector("[data-irv-kind]"),
    title: root.querySelector("[data-irv-title]"),
    context: root.querySelector("[data-irv-context]"),
    options: root.querySelector("[data-irv-options]"),
    rows: root.querySelector("[data-irv-rows]"),
    voters: root.querySelector("[data-irv-voters]"),
    note: root.querySelector("[data-irv-note]"),
    live: root.querySelector("[data-irv-live]"),
    winner: root.querySelector("[data-irv-winner]"),
    winnerName: root.querySelector("[data-irv-winner-name]"),
    winnerCopy: root.querySelector("[data-irv-winner-copy]"),
    round: root.querySelector("[data-irv-round]"),
    phase: root.querySelector("[data-irv-phase]"),
    seed: root.querySelector("[data-irv-seed]"),
    power: root.querySelector("[data-irv-power]"),
    continuing: root.querySelector("[data-irv-continuing]"),
  };

  let runId = 0;
  let activeToken = null;

  function sleep(ms, token) {
    if (ms <= 0) return Promise.resolve();
    return new Promise(function (resolve) {
      const timer = setTimeout(resolve, ms);
      token.cancel = function () {
        clearTimeout(timer);
        resolve();
      };
    });
  }

  function alive(token) {
    return token.id === runId;
  }

  function setPhase(label, eliminating) {
    els.phase.textContent = label;
    els.phase.parentElement.classList.toggle("is-elim", !!eliminating);
    els.note.classList.toggle("is-elim", !!eliminating);
  }

  function optionById(scenario, id) {
    return scenario.options.find(function (option) {
      return option.id === id;
    });
  }

  function keyFor(scenario, id) {
    return window.IRV.optionKey(scenario.options.findIndex(function (option) {
      return option.id === id;
    }));
  }

  function renderProposal(scenario) {
    els.kind.textContent = scenario.kind;
    els.title.innerHTML = scenario.title.replace(/([?.])$/, "<em>$1</em>");
    els.context.textContent = scenario.context;
    els.options.innerHTML = scenario.options
      .map(function (option, index) {
        return (
          '<li class="sim-option" data-option="' +
          option.id +
          '"><span class="sim-key">' +
          window.IRV.optionKey(index) +
          '</span><span><span class="sim-option-name">' +
          option.name +
          '</span><span class="sim-option-blurb">' +
          option.blurb +
          "</span></span></li>"
        );
      })
      .join("");
  }

  function renderChart(scenario) {
    els.rows.innerHTML = scenario.options
      .map(function (option, index) {
        return (
          '<div class="sim-row" data-option="' +
          option.id +
          '"><div class="sim-row-label">' +
          window.IRV.optionKey(index) +
          " · " +
          option.name +
          '</div><div class="sim-track"><div class="sim-bar" data-bar></div><div class="sim-majority" aria-hidden="true"><span>Majority</span></div><span class="sim-transfer" data-transfer></span></div><div class="sim-value" data-value>0</div></div>'
        );
      })
      .join("");
  }

  function renderVoters(scenario, voters) {
    const maxPower = Math.max.apply(
      null,
      voters.map(function (voter) {
        return voter.power;
      })
    );
    els.voters.innerHTML = voters
      .map(function (voter) {
        const first = voter.ranking[0];
        return (
          '<div class="sim-voter' +
          (voter.power >= maxPower * 0.72 ? " is-heavy" : "") +
          '" data-voter="' +
          voter.id +
          '"><span class="sim-voter-name">' +
          voter.name +
          '</span><span class="sim-voter-meta"><span>' +
          voter.power +
          ' vp</span><span data-choice>' +
          keyFor(scenario, first) +
          "</span></span></div>"
        );
      })
      .join("");
  }

  function clearMarks(selector, className) {
    root.querySelectorAll(selector).forEach(function (node) {
      node.classList.remove(className);
    });
  }

  function applyOptionState(id, className, on) {
    root.querySelectorAll('[data-option="' + id + '"]').forEach(function (node) {
      node.classList.toggle(className, on);
    });
  }

  function setBars(round, animateFromZero) {
    const continuing = round.continuing || 1;
    round.remaining.forEach(function (id) {
      const row = els.rows.querySelector('[data-option="' + id + '"]');
      if (!row) return;
      const bar = row.querySelector("[data-bar]");
      const value = row.querySelector("[data-value]");
      const votes = round.tallies[id] || 0;
      const pct = (votes / continuing) * 100;
      if (animateFromZero) {
        bar.style.width = "0%";
        bar.offsetWidth;
      }
      bar.style.width = pct + "%";
      value.textContent = String(votes);
    });
  }

  function markLead(round) {
    clearMarks(".sim-row, .sim-option", "is-lead");
    let leadId = null;
    let leadVotes = -1;
    round.remaining.forEach(function (id) {
      const votes = round.tallies[id] || 0;
      if (votes > leadVotes) {
        leadVotes = votes;
        leadId = id;
      }
    });
    if (leadId) applyOptionState(leadId, "is-lead", true);
  }

  function updateVoterChoices(scenario, voters, remaining) {
    const remainingSet = new Set(remaining);
    voters.forEach(function (voter) {
      const node = els.voters.querySelector('[data-voter="' + voter.id + '"]');
      if (!node) return;
      const choice = window.IRV.currentChoice(voter.ranking, remainingSet);
      const label = node.querySelector("[data-choice]");
      label.textContent = choice ? keyFor(scenario, choice) : "—";
      node.classList.toggle("is-active", !!choice);
    });
  }

  function setNote(text) {
    els.note.innerHTML = text;
    els.live.textContent = text.replace(/<[^>]+>/g, "");
  }

  function showWinner(scenario, runoff) {
    const winner = optionById(scenario, runoff.winnerId);
    els.winner.classList.add("is-on");
    els.winnerName.innerHTML = winner.name.replace(/(\S+)$/, "<em>$1</em>");
    els.winnerCopy.textContent = runoff.recap.summary;
    applyOptionState(runoff.winnerId, "is-winner", true);
    applyOptionState(runoff.winnerId, "is-lead", true);
  }

  function syncUrl(seedLabel) {
    const url = new URL(window.location.href);
    url.searchParams.set("seed", seedLabel);
    window.history.replaceState({}, "", url);
  }

  function readSeed() {
    const url = new URL(window.location.href);
    return url.searchParams.get("seed") || String((Date.now() ^ (Math.random() * 0xffffffff)) >>> 0);
  }

  async function play(seedValue) {
    if (activeToken) activeToken.cancel();
    const token = { id: ++runId, cancel: function () {} };
    activeToken = token;
    const model = window.IRV.simulate(seedValue);
    const timing = window.IRV.timingFor(model.runoff.rounds, reducedMotion);
    const scenario = model.scenario;
    const voters = model.voters;
    const runoff = model.runoff;

    els.winner.classList.remove("is-on");
    clearMarks(".sim-row, .sim-option, .sim-voter", "is-lead");
    clearMarks(".sim-row, .sim-option", "is-eliminating");
    clearMarks(".sim-row, .sim-option", "is-out");
    clearMarks(".sim-row, .sim-option", "is-winner");
    clearMarks(".sim-row", "is-receiving");
    clearMarks(".sim-voter", "is-moving");

    els.round.textContent = "00";
    els.seed.textContent = model.seedLabel;
    els.power.textContent = String(runoff.totalPower);
    els.continuing.textContent = "—";
    setPhase("Proposal agent");
    setNote("A proposal agent is selecting a governance scenario from the curated bank.");
    renderProposal(scenario);
    renderChart(scenario);
    els.voters.innerHTML = "";
    syncUrl(model.seedLabel);

    await sleep(timing.compose, token);
    if (!alive(token)) return;

    setPhase("Ballots in");
    setNote("Voter agents are casting full ranked ballots. A few hold visibly more voting power.");
    renderVoters(scenario, voters);
    await sleep(timing.ballots, token);
    if (!alive(token)) return;

    for (let i = 0; i < runoff.rounds.length; i += 1) {
      const round = runoff.rounds[i];
      const isFinal = i === runoff.rounds.length - 1 && !!round.majorityId;
      els.round.textContent = String(round.index).padStart(2, "0");
      els.continuing.textContent = String(round.continuing);
      setBars(round, i === 0);
      markLead(round);
      updateVoterChoices(scenario, voters, round.remaining);
      setPhase(isFinal ? "Majority" : "Round " + round.index);
      setNote(window.IRV.roundExplainer(scenario.options, round, isFinal));

      await sleep(timing.read, token);
      if (!alive(token)) return;

      if (round.eliminated) {
        setPhase("Eliminating", true);
        applyOptionState(round.eliminated, "is-eliminating", true);
        applyOptionState(round.eliminated, "is-lead", false);
        (round.transfers.movers || []).forEach(function (voterId) {
          const node = els.voters.querySelector('[data-voter="' + voterId + '"]');
          if (node) node.classList.add("is-moving");
        });
        Object.keys(round.transfers.flows).forEach(function (destId) {
          const amount = round.transfers.flows[destId];
          if (!amount) return;
          const row = els.rows.querySelector('[data-option="' + destId + '"]');
          if (!row) return;
          row.classList.add("is-receiving");
          row.querySelector("[data-transfer]").textContent = "+" + amount;
        });
        await sleep(timing.flash, token);
        if (!alive(token)) return;

        applyOptionState(round.eliminated, "is-out", true);
        applyOptionState(round.eliminated, "is-eliminating", false);
        const outRow = els.rows.querySelector('[data-option="' + round.eliminated + '"]');
        if (outRow) {
          outRow.querySelector("[data-bar]").style.width = "0%";
          outRow.querySelector("[data-value]").textContent = "0";
        }
        const next = runoff.rounds[i + 1];
        if (next) {
          setBars(next, false);
          markLead(next);
          updateVoterChoices(scenario, voters, next.remaining);
        }

        await sleep(timing.transfer, token);
        if (!alive(token)) return;
        clearMarks(".sim-row", "is-receiving");
        clearMarks(".sim-voter", "is-moving");
      }
    }

    showWinner(scenario, runoff);
    setPhase("Winner");
    await sleep(timing.reveal, token);
  }

  function restart() {
    const seed = (crypto.getRandomValues(new Uint32Array(1))[0] >>> 0).toString(16);
    play(seed);
  }

  els.generate.forEach(function (button) {
    button.addEventListener("click", restart);
  });

  play(readSeed());
})();
