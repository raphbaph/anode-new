const canvas = document.querySelector("#coordination-canvas");
const hero = document.querySelector(".hero");
const ctx = canvas.getContext("2d");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const pointer = { x: 0, y: 0, active: false, lastMoveAt: 0 };
const field = { width: 0, height: 0, dpr: 1, agents: [], sparks: [] };

function resizeField() {
  field.width = canvas.clientWidth;
  field.height = canvas.clientHeight;
  field.dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = field.width * field.dpr;
  canvas.height = field.height * field.dpr;
  ctx.setTransform(field.dpr, 0, 0, field.dpr, 0, 0);

  if (!pointer.active) {
    pointer.x = field.width * 0.73;
    pointer.y = field.height * 0.42;
  }
}

function createAgent(index) {
  const angle = Math.random() * Math.PI * 2;
  const radius = 40 + Math.random() * Math.min(field.width, field.height) * 0.26;
  const centerX = field.width * 0.69;
  const centerY = field.height * 0.44;
  const startX = centerX + Math.cos(angle) * radius * (1.45 + Math.random() * 0.6);
  const startY = centerY + Math.sin(angle) * radius * 0.57;
  return {
    x: startX,
    y: startY,
    homeX: startX,
    homeY: startY,
    vx: (Math.random() - 0.5) * 0.7,
    vy: (Math.random() - 0.5) * 0.7,
    size: 3.4 + Math.random() * 4.8,
    tint: index % 8 === 0 ? "#c4f545" : index % 3 === 0 ? "#8ca595" : "#466358",
    phase: Math.random() * Math.PI * 2,
    orbit: 0.3 + Math.random() * 1.25,
    wander: 0.65 + Math.random() * 0.9,
  };
}

function seedField() {
  const count = Math.max(72, Math.min(145, Math.floor(field.width / 9)));
  field.agents = Array.from({ length: count }, (_, index) => createAgent(index));
  field.sparks = Array.from({ length: Math.floor(count * 0.35) }, () => ({
    x: field.width * (0.48 + Math.random() * 0.48),
    y: field.height * (0.12 + Math.random() * 0.65),
    size: 0.5 + Math.random() * 1.8,
    phase: Math.random() * Math.PI * 2,
  }));
}

function drawAgent(agent, time) {
  const speed = Math.hypot(agent.vx, agent.vy);
  const angle = Math.atan2(agent.vy, agent.vx);
  const pulse = 0.75 + Math.sin(time * 0.002 + agent.phase) * 0.25;
  ctx.save();
  ctx.translate(agent.x, agent.y);
  ctx.rotate(angle);
  ctx.globalAlpha = Math.min(0.9, 0.35 + speed * 0.4) * pulse;
  ctx.fillStyle = agent.tint;
  ctx.beginPath();
  ctx.moveTo(agent.size * 2.8, 0);
  ctx.lineTo(-agent.size * 1.4, -agent.size * 0.95);
  ctx.lineTo(-agent.size * 0.8, 0);
  ctx.lineTo(-agent.size * 1.4, agent.size * 0.95);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function animate(time) {
  if (pointer.active && time - pointer.lastMoveAt > 900) releaseAgents();
  ctx.clearRect(0, 0, field.width, field.height);
  const centerX = field.width * 0.69;
  const centerY = field.height * 0.44;
  const targetX = pointer.active ? pointer.x : centerX + Math.sin(time * 0.00025) * 80;
  const targetY = pointer.active ? pointer.y : centerY + Math.cos(time * 0.00035) * 55;

  field.sparks.forEach((spark) => {
    const alpha = 0.2 + (Math.sin(time * 0.001 + spark.phase) + 1) * 0.13;
    ctx.fillStyle = `rgba(196, 245, 69, ${alpha})`;
    ctx.beginPath();
    ctx.arc(spark.x, spark.y, spark.size, 0, Math.PI * 2);
    ctx.fill();
  });

  field.agents.forEach((agent, index) => {
    const idleTargetX = agent.homeX + Math.sin(time * 0.00017 + agent.phase * 1.7) * 82 * agent.wander;
    const idleTargetY = agent.homeY + Math.cos(time * 0.00021 + agent.phase * 1.3) * 58 * agent.wander;
    const destinationX = pointer.active ? targetX : idleTargetX;
    const destinationY = pointer.active ? targetY : idleTargetY;
    const dx = destinationX - agent.x;
    const dy = destinationY - agent.y;
    const distance = Math.max(35, Math.hypot(dx, dy));
    const pull = pointer.active ? 0.00068 : 0.0003;
    const orbitX = Math.cos(time * 0.00025 + agent.phase) * agent.orbit;
    const orbitY = Math.sin(time * 0.00031 + agent.phase) * agent.orbit;
    agent.vx += (dx / distance) * pull * distance + orbitX * 0.004;
    agent.vy += (dy / distance) * pull * distance + orbitY * 0.004;
    if (!pointer.active) {
      let separationX = 0;
      let separationY = 0;
      field.agents.forEach((other) => {
        if (other === agent) return;
        const separationDx = agent.x - other.x;
        const separationDy = agent.y - other.y;
        const separationDistance = Math.hypot(separationDx, separationDy);
        if (separationDistance === 0 || separationDistance > 70) return;
        const separationForce = ((70 - separationDistance) / 70) * 0.03;
        separationX += (separationDx / separationDistance) * separationForce;
        separationY += (separationDy / separationDistance) * separationForce;
      });
      agent.vx += separationX + Math.cos(time * 0.00043 + agent.phase * 2.1) * 0.012 * agent.wander;
      agent.vy += separationY + Math.sin(time * 0.00037 + agent.phase * 1.8) * 0.012 * agent.wander;
    }
    agent.vx *= 0.975;
    agent.vy *= 0.975;

    const maxSpeed = pointer.active ? 2.45 : 1.8;
    const speed = Math.hypot(agent.vx, agent.vy);
    if (speed > maxSpeed) {
      agent.vx = (agent.vx / speed) * maxSpeed;
      agent.vy = (agent.vy / speed) * maxSpeed;
    }
    agent.x += agent.vx;
    agent.y += agent.vy;

    if (agent.x < -30) agent.x = field.width + 30;
    if (agent.x > field.width + 30) agent.x = -30;
    if (agent.y < -30) agent.y = field.height + 30;
    if (agent.y > field.height + 30) agent.y = -30;

    if (pointer.active && index % 11 === 0) {
      ctx.strokeStyle = "rgba(196, 245, 69, .055)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(agent.x, agent.y);
      ctx.lineTo(targetX, targetY);
      ctx.stroke();
    }
    drawAgent(agent, time);
  });

  if (pointer.active) {
    const glow = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 90);
    glow.addColorStop(0, "rgba(196, 245, 69, .14)");
    glow.addColorStop(1, "rgba(196, 245, 69, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(pointer.x, pointer.y, 90, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(196, 245, 69, .7)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(pointer.x, pointer.y, 10 + Math.sin(time * 0.004) * 2, 0, Math.PI * 2);
    ctx.stroke();
  }

  if (!reducedMotion) requestAnimationFrame(animate);
}

hero.addEventListener("pointermove", (event) => {
  const rect = canvas.getBoundingClientRect();
  pointer.x = event.clientX - rect.left;
  pointer.y = event.clientY - rect.top;
  pointer.active = true;
  pointer.lastMoveAt = performance.now();
});

function releaseAgents() {
  if (!pointer.active) return;

  const center = field.agents.reduce(
    (accumulator, agent) => ({ x: accumulator.x + agent.x, y: accumulator.y + agent.y }),
    { x: 0, y: 0 },
  );
  center.x /= field.agents.length;
  center.y /= field.agents.length;

  field.agents.forEach((agent, index) => {
    const angle = agent.phase + index * 0.37;
    const dx = agent.x - center.x;
    const dy = agent.y - center.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const outwardX = distance > 8 ? dx / distance : Math.cos(angle);
    const outwardY = distance > 8 ? dy / distance : Math.sin(angle);
    const releaseRadius = 80 + Math.random() * 220;
    agent.homeX = center.x + Math.cos(angle) * releaseRadius * 1.15;
    agent.homeY = center.y + Math.sin(angle) * releaseRadius * 0.72;
    const impulse = 1.1 + Math.random() * 0.8;
    agent.vx += (outwardX * 0.9 + Math.cos(angle) * 0.35) * impulse;
    agent.vy += (outwardY * 0.9 + Math.sin(angle) * 0.35) * impulse;
  });

  pointer.active = false;
}

hero.addEventListener("pointerleave", releaseAgents);
window.addEventListener("resize", () => { resizeField(); seedField(); });

resizeField();
seedField();
animate(0);
