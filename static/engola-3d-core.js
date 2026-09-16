import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js";

(() => {
  const host = document.getElementById("engolaCore");
  if (!host) return;

  host.innerHTML = "";

  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(
    35,
    Math.max(host.clientWidth, 1) / Math.max(host.clientHeight, 1),
    0.1,
    100
  );
  camera.position.set(0, 0, 5);

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
  });

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(
    Math.max(host.clientWidth, 1),
    Math.max(host.clientHeight, 1),
    false
  );
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;

  host.appendChild(renderer.domElement);

  const group = new THREE.Group();
  scene.add(group);

  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(1.18, 96, 96),
    new THREE.MeshPhysicalMaterial({
      color: 0x7c5cff,
      emissive: 0x24104f,
      emissiveIntensity: 0.65,
      roughness: 0.16,
      metalness: 0.18,
      transmission: 0.08,
      thickness: 0.45,
      clearcoat: 1,
      clearcoatRoughness: 0.12,
    })
  );
  group.add(sphere);

  const inner = new THREE.Mesh(
    new THREE.SphereGeometry(0.88, 64, 64),
    new THREE.MeshBasicMaterial({
      color: 0x67e8f9,
      transparent: true,
      opacity: 0.10,
      blending: THREE.AdditiveBlending,
    })
  );
  group.add(inner);

  const orbitMaterials = [
    new THREE.MeshBasicMaterial({
      color: 0xa78bfa,
      transparent: true,
      opacity: 0.8,
    }),
    new THREE.MeshBasicMaterial({
      color: 0x67e8f9,
      transparent: true,
      opacity: 0.65,
    }),
    new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.3,
    }),
  ];

  const orbits = [];

  [
    [1.48, 0.42, 0.15],
    [1.68, 1.05, -0.4],
    [1.88, -0.55, 0.72],
  ].forEach(([radius, rx, rz], i) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(radius, 0.012, 12, 128),
      orbitMaterials[i]
    );

    ring.rotation.x = rx;
    ring.rotation.z = rz;

    group.add(ring);
    orbits.push(ring);
  });

  const nodeGeometry = new THREE.SphereGeometry(0.075, 24, 24);

  const nodes = [
    [1.52, 0.15, 0.18],
    [-1.42, -0.38, 0.28],
    [0.2, 1.62, -0.2],
    [-0.25, -1.65, 0.25],
  ].map(([x, y, z], i) => {
    const material = new THREE.MeshBasicMaterial({
      color: i % 2 ? 0x67e8f9 : 0xa78bfa,
    });

    const node = new THREE.Mesh(nodeGeometry, material);
    node.position.set(x, y, z);
    group.add(node);
    return node;
  });

  scene.add(
    new THREE.AmbientLight(0xffffff, 0.45)
  );

  const key = new THREE.PointLight(0xa78bfa, 14, 10);
  key.position.set(2.4, 2.2, 3.4);
  scene.add(key);

  const fill = new THREE.PointLight(0x67e8f9, 9, 9);
  fill.position.set(-2.4, -1.5, 2.5);
  scene.add(fill);

  let targetX = 0;
  let targetY = 0;

  window.addEventListener("pointermove", (event) => {
    const x = event.clientX / window.innerWidth;
    const y = event.clientY / window.innerHeight;

    targetX = (x - 0.5) * 0.45;
    targetY = (y - 0.5) * 0.35;
  });

  const resize = () => {
    const width = Math.max(host.clientWidth, 1);
    const height = Math.max(host.clientHeight, 1);

    camera.aspect = width / height;
    camera.updateProjectionMatrix();

    renderer.setSize(width, height, false);
  };

  window.addEventListener("resize", resize);
  resize();

  let state = "idle";

  window.Engola3D = {
    setState(next) {
      state = next || "idle";
    }
  };

  const clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);

    const t = clock.getElapsedTime();

    group.rotation.y += 0.0018;
    group.rotation.x += (targetY * 0.12 - group.rotation.x) * 0.025;

    group.position.x += (targetX * 0.18 - group.position.x) * 0.025;

    sphere.scale.setScalar(
      1 + Math.sin(t * 1.7) * 0.018
    );

    inner.scale.setScalar(
      1 + Math.sin(t * 2.4) * 0.035
    );

    orbits[0].rotation.y += 0.006;
    orbits[1].rotation.y -= 0.004;
    orbits[2].rotation.x += 0.003;

    nodes.forEach((node, i) => {
      const phase = t * (1.2 + i * 0.12) + i;
      node.position.y += Math.sin(phase) * 0.0009;
    });

    const intensity = {
      idle: 1,
      thinking: 1.55,
      speaking: 1.3,
      success: 1.8,
      error: 0.75,
    }[state] || 1;

    key.intensity = 14 * intensity;
    fill.intensity = 9 * intensity;

    renderer.render(scene, camera);
  }

  animate();
})();
