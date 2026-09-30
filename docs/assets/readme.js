// An offline illustration, never a connection to a real farm.
const root = document.documentElement;
const themeButton = document.querySelector('#theme-toggle');
const themeLabel = themeButton.querySelector('span');
const setTheme = theme => {
  root.dataset.theme = theme;
  const next = theme === 'dark' ? 'Daylight' : 'Firelight';
  themeLabel.textContent = next;
  themeButton.setAttribute('aria-label', `Switch to ${next} theme`);
};
try {
  const stored = localStorage.getItem('hearth-readme-theme');
  if (stored === 'dark' || stored === 'light') setTheme(stored);
} catch { /* The page also works with file storage blocked. */ }
themeButton.hidden = false;
themeButton.addEventListener('click', () => {
  setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
  try { localStorage.setItem('hearth-readme-theme', root.dataset.theme); } catch { /* Optional preference. */ }
});

const descriptions = {
  all: ['A capability is a destination, not a computer.', 'Each node is a job your farm can do. Dotted boundaries group the capabilities hosted on one machine. Add providers on separate machines to grow the farm without forcing them to take turns.'],
  chat: ['A conversation goes to a qualified model target.', 'hearth routes text work to an available, verified target on the model host. Conversation and Coding may bind to the same compatible model. An independently resourced media worker can keep creating while you talk.'],
  image: ['One image queue, wherever the idea starts.', 'Direct image requests from private chat, shared channels and the image page use the media queue. On this example shared GPU, the scheduler gives owners a fair turn and prepares Fooocus when its job is selected.'],
  geometry: ['Choose a 3D backend. Let the worker make room.', 'An image-to-3D job targets either TRELLIS.2 or Hunyuan3D 2.0. On this example shared GPU, the media scheduler switches backends for the selected job. Move services to separate hosts when you have capacity for concurrent work.'],
};
const tree = document.querySelector('.farm-tree');
const controls = document.querySelector('.route-controls');
controls.hidden = false;
controls.addEventListener('click', event => {
  const button = event.target.closest('button[data-route]');
  if (!button) return;
  const route = button.dataset.route;
  tree.dataset.route = route;
  for (const option of controls.querySelectorAll('button')) option.setAttribute('aria-pressed', String(option === button));
  document.querySelector('#route-title').textContent = descriptions[route][0];
  document.querySelector('#route-description').textContent = descriptions[route][1];
});

// Measure the machine boxes so the branches survive responsive layout and text resizing.
function drawConnections() {
  const canvas = tree.getBoundingClientRect();
  const head = document.querySelector('#head-machine').getBoundingClientRect();
  const startX = head.left + head.width / 2 - canvas.left;
  const startY = head.bottom - canvas.top;
  const stacked = matchMedia('(max-width: 800px)').matches;
  for (const [name, selector] of [['text', '#text-machine'], ['media', '#media-machine']]) {
    const target = document.querySelector(selector).getBoundingClientRect();
    const endY = target.top - canvas.top;
    const endX = target.left + target.width / 2 - canvas.left;
    const elbowY = startY + (stacked ? 18 : (endY - startY) / 2);
    const laneX = target.left - canvas.left - 7;
    const d = stacked
      ? `M ${startX} ${startY} V ${elbowY} H ${laneX} V ${endY + 27} H ${target.left - canvas.left}`
      : `M ${startX} ${startY} V ${elbowY} H ${endX} V ${endY}`;
    document.querySelector(`.connection-${name}`).setAttribute('d', d);
  }
}
new ResizeObserver(drawConnections).observe(tree);
drawConnections();
