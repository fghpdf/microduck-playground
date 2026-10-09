import { useEffect, useRef, useState } from "react";
import { useI18n } from "./i18n";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Frame, Obstacle, Terrain, SceneObject, Goal } from "./api";
import { worldLayout, viewDistance, rampVertices } from "./world-layout";
import {
  objectPose,
  renderQuaternion,
  objectIndicatorAnchor,
} from "./object-pose";

interface ItemMeshEntry {
  id: string;
  kind: "ball" | "trash";
  mesh: THREE.Mesh;
  outline?: THREE.LineSegments;
  leader?: THREE.Line;
  sprite?: THREE.Sprite;
  texture?: THREE.CanvasTexture;
  canvas?: HTMLCanvasElement;
  context?: CanvasRenderingContext2D | null;
  lastAttached?: boolean;
  lastLabel?: string;
}

export default function World({
  frame,
  target,
  obstacles,
  terrain,
  objects,
  goal,
  objectPathPoints,
  pickupStart,
}: {
  frame?: Frame;
  target?: [number, number];
  obstacles?: Obstacle[];
  terrain?: Terrain[];
  objects?: SceneObject[];
  goal?: Goal;
  objectPathPoints?: [number, number, number][];
  pickupStart?: [number, number, number];
}) {
  const { t, locale } = useI18n();
  const layoutKey = JSON.stringify([
    target,
    obstacles,
    terrain,
    objectPathPoints,
  ]);
  const layout = useRef(
    worldLayout(target, obstacles, terrain, objectPathPoints),
  );
  const fitView = useRef<(() => void) | null>(null);
  const setTopView = useRef<(() => void) | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const robot = useRef<THREE.Group | null>(null);
  const joints = useRef<
    { node: THREE.Group; index: number; axis: "x" | "y" | "z" }[]
  >([]);
  const terrainGroup = useRef<THREE.Group | null>(null);
  const obstacleGroup = useRef<THREE.Group | null>(null);
  const marker = useRef<THREE.Mesh | null>(null);
  const ball = useRef<THREE.Mesh | null>(null);
  const itemGroup = useRef<THREE.Group | null>(null);
  const itemsMap = useRef<Map<string, ItemMeshEntry>>(new Map());
  const goalGroup = useRef<THREE.Group | null>(null);
  const pickupGroup = useRef<THREE.Group | null>(null);

  const [unsupported, setUnsupported] = useState(false);
  const [activeCameraMode, setActiveCameraMode] = useState<
    "free" | "follow" | "top"
  >("free");
  const cameraModeRef = useRef<"free" | "follow" | "top">("free");
  cameraModeRef.current = activeCameraMode;

  useEffect(() => {
    if (!host.current) return;
    const node = host.current;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setUnsupported(true);
      return;
    }
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#eeeade");
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
    camera.position.set(1.8, -2.6, 1.8);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0.3, 0, 0.25);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.48;

    fitView.current = () => {
      camera.up.set(0, 0, 1);
      const center = new THREE.Vector3(...layout.current.center);
      const direction = new THREE.Vector3(1.5, -2.6, 1.55).normalize();
      controls.target.copy(center);
      camera.position
        .copy(center)
        .addScaledVector(
          direction,
          viewDistance(layout.current.radius, camera.aspect),
        );
      controls.update();
    };

    setTopView.current = () => {
      camera.up.set(0, 1, 0);
      const center = new THREE.Vector3(...layout.current.center);
      controls.target.copy(center);
      const dist = viewDistance(layout.current.radius, camera.aspect) * 1.25;
      camera.position.set(center.x, center.y, center.z + dist);
      controls.update();
    };

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    node.appendChild(renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9d8b74, 3));
    const light = new THREE.DirectionalLight(0xffffff, 4);
    light.position.set(2, -3, 6);
    light.castShadow = true;
    scene.add(light);
    const material = (color: string) =>
      new THREE.MeshStandardMaterial({ color, roughness: 0.65 });
    const group = new THREE.Group();
    const mesh = (
      geometry: THREE.BufferGeometry,
      color: string,
      x: number,
      y: number,
      z: number,
    ) => {
      const m = new THREE.Mesh(geometry, material(color));
      m.position.set(x, y, z - 0.29);
      m.castShadow = true;
      group.add(m);
      return m;
    };
    mesh(new THREE.BoxGeometry(0.23, 0.17, 0.17), "#f4f2e9", 0, 0, 0.29);
    mesh(new THREE.BoxGeometry(0.17, 0.17, 0.13), "#ff9d32", 0.06, 0, 0.45);
    mesh(new THREE.BoxGeometry(0.1, 0.14, 0.04), "#ec762a", 0.17, 0, 0.42);
    joints.current = [];
    for (const [side, y] of [
      [0, -0.062],
      [10, 0.062],
    ]) {
      mesh(new THREE.SphereGeometry(0.013, 12, 8), "#292b30", 0.13, y, 0.48);
      let parent: THREE.Group = group;
      const axes = ["z", "x", "y", "y", "y"] as const;
      for (let n = 0; n < 5; n++) {
        const pivot = new THREE.Group();
        pivot.position.set(
          0,
          n === 0 ? y : 0,
          n === 0 ? -0.015 : n < 3 ? 0 : -0.045,
        );
        parent.add(pivot);
        joints.current.push({ node: pivot, index: side + n, axis: axes[n] });
        if (n >= 2) {
          const segment = new THREE.Mesh(
            new THREE.BoxGeometry(
              n === 4 ? 0.12 : 0.035,
              0.035,
              n === 4 ? 0.025 : 0.045,
            ),
            material(n === 4 ? "#3e4644" : "#8e9696"),
          );
          segment.position.set(n === 4 ? 0.035 : 0, 0, n === 4 ? 0 : -0.0225);
          segment.castShadow = true;
          pivot.add(segment);
        }
        parent = pivot;
      }
    }
    robot.current = group;
    scene.add(group);
    obstacleGroup.current = new THREE.Group();
    scene.add(obstacleGroup.current);
    terrainGroup.current = new THREE.Group();
    scene.add(terrainGroup.current);
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 20),
      material("#eeeade"),
    );
    ground.receiveShadow = true;
    scene.add(ground);
    const grid = new THREE.GridHelper(12, 24, 0xc9c3b4, 0xded8cb);
    grid.rotateX(Math.PI / 2);
    grid.position.z = 0.002;
    scene.add(grid);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.15, 0.2, 48),
      new THREE.MeshBasicMaterial({ color: "#e78337", side: THREE.DoubleSide }),
    );
    ring.position.z = 0.009;
    marker.current = ring;
    scene.add(ring);
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.035, 24, 16),
      material("#91a19a"),
    );
    sphere.visible = false;
    ball.current = sphere;
    scene.add(sphere);
    itemGroup.current = new THREE.Group();
    goalGroup.current = new THREE.Group();
    scene.add(itemGroup.current, goalGroup.current);
    pickupGroup.current = new THREE.Group();
    scene.add(pickupGroup.current);
    const resize = () => {
      const { width, height } = node.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
      if (cameraModeRef.current !== "top") {
        fitView.current?.();
      } else {
        setTopView.current?.();
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(node);
    resize();
    let id = 0;
    const animate = () => {
      if (cameraModeRef.current === "follow" && robot.current) {
        const rp = robot.current.position;
        controls.target.set(rp.x, rp.y, rp.z + 0.1);
      }
      controls.update();
      renderer.render(scene, camera);
      id = requestAnimationFrame(animate);
    };
    animate();
    return () => {
      cancelAnimationFrame(id);
      observer.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        if (
          o instanceof THREE.Mesh ||
          o instanceof THREE.LineSegments ||
          o instanceof THREE.Line ||
          o instanceof THREE.Sprite
        ) {
          o.geometry?.dispose();
          const ms = Array.isArray(o.material) ? o.material : [o.material];
          ms.forEach((m) => {
            if ("map" in m && m.map && m.map instanceof THREE.Texture) {
              m.map.dispose();
            }
            m.dispose();
          });
        }
      });
      itemsMap.current.clear();
      terrainGroup.current = null;
      obstacleGroup.current = null;
      itemGroup.current = null;
      fitView.current = null;
      setTopView.current = null;
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  useEffect(() => {
    const [goal, boxes, ramps, paths] = JSON.parse(layoutKey) as [
      [number, number] | null,
      Obstacle[] | null,
      Terrain[] | null,
      [number, number, number][] | null,
    ];
    layout.current = worldLayout(
      goal ?? undefined,
      boxes ?? [],
      ramps ?? [],
      paths ?? [],
    );
    if (cameraModeRef.current === "top") {
      setTopView.current?.();
    } else {
      fitView.current?.();
    }
  }, [layoutKey]);

  useEffect(() => {
    if (robot.current) {
      robot.current.position.fromArray(frame?.position ?? [0, 0, 0.29]);
      const q = frame?.quaternion ?? [1, 0, 0, 0];
      robot.current.quaternion.set(q[1], q[2], q[3], q[0]);
      joints.current.forEach(({ node, index, axis }) => {
        node.rotation[axis] = frame?.joints[index] ?? 0;
      });
    }
    if (marker.current)
      marker.current.position.set(target?.[0] ?? 1, target?.[1] ?? 0, 0.009);
    if (ball.current) {
      ball.current.visible = !!frame?.ball && !objects?.length;
      if (frame?.ball) ball.current.position.fromArray(frame.ball);
    }
  }, [frame, target, objects]);

  useEffect(() => {
    const group = obstacleGroup.current;
    if (!group) return;
    const meshes = (obstacles ?? []).map((obstacle) => {
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(...obstacle.size),
        new THREE.MeshStandardMaterial({ color: "#718792", roughness: 0.8 }),
      );
      m.position.fromArray(obstacle.position);
      m.rotation.z = obstacle.yaw;
      m.castShadow = true;
      m.receiveShadow = true;
      group.add(m);
      return m;
    });
    return () => {
      meshes.forEach((m) => {
        group.remove(m);
        m.geometry.dispose();
        m.material.dispose();
      });
    };
  }, [obstacles]);

  useEffect(() => {
    const group = terrainGroup.current;
    if (!group) return;
    const objects = (terrain ?? []).flatMap((ramp) => {
      const vertices = rampVertices(ramp);
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(vertices.flat(), 3),
      );
      geometry.setIndex([
        0, 2, 1, 3, 4, 5, 0, 1, 4, 0, 4, 3, 1, 2, 5, 1, 5, 4, 0, 3, 5, 0, 5, 2,
      ]);
      geometry.computeVertexNormals();
      const m = new THREE.Mesh(
        geometry,
        new THREE.MeshStandardMaterial({
          color: "#d6b66e",
          roughness: 0.85,
          side: THREE.DoubleSide,
        }),
      );
      m.receiveShadow = true;
      m.castShadow = true;
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: "#866831" }),
      );
      const guidePoints: THREE.Vector3[] = [];
      for (const fraction of [0.2, 0.4, 0.6, 0.8]) {
        const x =
          ramp.position[0] + ramp.direction * ramp.size[0] * (fraction - 0.5);
        const z = ramp.position[2] + ramp.size[2] * fraction + 0.001;
        guidePoints.push(
          new THREE.Vector3(x, ramp.position[1] - ramp.size[1] / 2, z),
          new THREE.Vector3(x, ramp.position[1] + ramp.size[1] / 2, z),
        );
      }
      const guides = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints(guidePoints),
        new THREE.LineBasicMaterial({ color: "#a4884f" }),
      );
      group.add(m, edges, guides);
      return [m, edges, guides];
    });
    return () =>
      objects.forEach((object) => {
        group.remove(object);
        object.geometry.dispose();
        object.material.dispose();
      });
  }, [terrain]);

  // 物体网格实例缓存与平滑复用（消除回放时反复重建 Canvas 与 Mesh 导致的 GC 卡顿）
  useEffect(() => {
    const group = itemGroup.current;
    if (!group) return;
    const currentList = frame?.objects ?? objects ?? [];
    const currentIds = new Set(currentList.map((item) => item.id));

    // 清理已移除的对象
    for (const [id, entry] of itemsMap.current.entries()) {
      if (!currentIds.has(id)) {
        group.remove(entry.mesh);
        if (entry.outline) group.remove(entry.outline);
        if (entry.leader) group.remove(entry.leader);
        if (entry.sprite) group.remove(entry.sprite);
        entry.mesh.geometry.dispose();
        (entry.mesh.material as THREE.Material).dispose();
        entry.outline?.geometry.dispose();
        (entry.outline?.material as THREE.Material | undefined)?.dispose();
        entry.leader?.geometry.dispose();
        (entry.leader?.material as THREE.Material | undefined)?.dispose();
        entry.sprite?.geometry.dispose();
        (entry.sprite?.material as THREE.Material | undefined)?.dispose();
        entry.texture?.dispose();
        itemsMap.current.delete(id);
      }
    }

    currentList.forEach((recorded) => {
      const item = objectPose(recorded, objects);
      let entry = itemsMap.current.get(item.id);

      if (!entry) {
        const geometry =
          item.kind === "ball"
            ? new THREE.SphereGeometry(item.radius ?? 0.035, 24, 16)
            : new THREE.BoxGeometry(...(item.size ?? [0.025, 0.025, 0.025]));
        const mesh = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: item.kind === "ball" ? "#f4f2e9" : "#ce7045",
            roughness: 0.8,
          }),
        );
        mesh.castShadow = true;
        group.add(mesh);

        let outline: THREE.LineSegments | undefined;
        let leader: THREE.Line | undefined;
        let sprite: THREE.Sprite | undefined;
        let texture: THREE.CanvasTexture | undefined;
        let canvas: HTMLCanvasElement | undefined;
        let context: CanvasRenderingContext2D | null = null;

        if (item.kind === "trash") {
          const isAttached = !!frame?.pickup?.attached;
          const color = isAttached ? "#1f8a71" : "#c8642c";
          outline = new THREE.LineSegments(
            new THREE.EdgesGeometry(geometry),
            new THREE.LineBasicMaterial({ color, depthTest: false }),
          );
          outline.renderOrder = 10;
          group.add(outline);

          leader = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([
              new THREE.Vector3(...item.position),
              new THREE.Vector3(...objectIndicatorAnchor(item.position)),
            ]),
            new THREE.LineBasicMaterial({ color, depthTest: false }),
          );
          leader.renderOrder = 11;
          group.add(leader);

          canvas = document.createElement("canvas");
          canvas.width = 192;
          canvas.height = 72;
          context = canvas.getContext("2d");
          if (context) {
            context.fillStyle = color;
            context.fillRect(0, 0, 192, 72);
            context.fillStyle = "white";
            context.font = "bold 36px sans-serif";
            context.textAlign = "center";
            context.textBaseline = "middle";
            context.fillText(
              t(isAttached ? "物品 · 夹持" : "物品"),
              96,
              36,
              180,
            );
          }
          texture = new THREE.CanvasTexture(canvas);
          sprite = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: texture,
              depthTest: false,
              depthWrite: false,
            }),
          );
          sprite.scale.set(0.14, 0.0525, 1);
          sprite.renderOrder = 12;
          group.add(sprite);
        }

        entry = {
          id: item.id,
          kind: item.kind,
          mesh,
          outline,
          leader,
          sprite,
          texture,
          canvas,
          context,
          lastAttached: !!frame?.pickup?.attached,
          lastLabel: t(frame?.pickup?.attached ? "物品 · 夹持" : "物品"),
        };
        itemsMap.current.set(item.id, entry);
      }

      // 更新位置与姿态
      entry.mesh.position.fromArray(item.position);
      entry.mesh.quaternion.fromArray(renderQuaternion(item.quaternion));

      if (entry.outline) {
        entry.outline.position.copy(entry.mesh.position);
        entry.outline.quaternion.copy(entry.mesh.quaternion);
      }

      const anchor = objectIndicatorAnchor(item.position);
      if (entry.leader) {
        entry.leader.geometry.setFromPoints([
          new THREE.Vector3(...item.position),
          new THREE.Vector3(...anchor),
        ]);
      }
      if (entry.sprite) {
        entry.sprite.position.fromArray(anchor);
      }

      // Redraw only when the grip state or translated label changes.
      const isAttached = !!frame?.pickup?.attached;
      const label = t(isAttached ? "物品 · 夹持" : "物品");
      if (
        (entry.lastAttached !== isAttached || entry.lastLabel !== label) &&
        entry.canvas &&
        entry.context &&
        entry.texture
      ) {
        entry.lastAttached = isAttached;
        entry.lastLabel = label;
        const color = isAttached ? "#1f8a71" : "#c8642c";
        entry.context.fillStyle = color;
        entry.context.fillRect(0, 0, 192, 72);
        entry.context.fillStyle = "white";
        entry.context.font = "bold 36px sans-serif";
        entry.context.textAlign = "center";
        entry.context.textBaseline = "middle";
        entry.context.fillText(
          t(isAttached ? "物品 · 夹持" : "物品"),
          96,
          36,
          180,
        );
        entry.texture.needsUpdate = true;
        if (entry.outline) {
          (entry.outline.material as THREE.LineBasicMaterial).color.set(color);
        }
        if (entry.leader) {
          (entry.leader.material as THREE.LineBasicMaterial).color.set(color);
        }
      }
    });
  }, [frame?.objects, objects, frame?.pickup?.attached, locale, t]);

  useEffect(() => {
    const group = goalGroup.current;
    if (!group || !goal) return;
    const meshes = [-1, 1].map((side) => {
      const m = new THREE.Mesh(
        new THREE.CylinderGeometry(0.009, 0.009, 0.15, 8),
        new THREE.MeshStandardMaterial({ color: "#ffffff" }),
      );
      m.rotateX(Math.PI / 2);
      m.position.set(goal.x, goal.y + (side * goal.width) / 2, 0.075);
      group.add(m);
      return m;
    });
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.018, goal.width, 0.018),
      new THREE.MeshStandardMaterial({ color: "#ffffff" }),
    );
    bar.position.set(goal.x, goal.y, 0.15);
    group.add(bar);
    const allMeshes = [...meshes, bar];
    return () =>
      allMeshes.forEach((m) => {
        group.remove(m);
        m.geometry.dispose();
        m.material.dispose();
      });
  }, [goal]);

  useEffect(() => {
    const group = pickupGroup.current;
    if (!group || !pickupStart || !target) return;
    const markers = [
      { text: "A", position: pickupStart, color: "#276f6c" },
      {
        text: "B",
        position: [target[0], target[1], 0] as [number, number, number],
        color: "#bc5d20",
      },
    ].map((entry) => {
      const canvas = document.createElement("canvas");
      canvas.width = 96;
      canvas.height = 96;
      const context = canvas.getContext("2d");
      if (context) {
        context.fillStyle = entry.color;
        context.beginPath();
        context.arc(48, 48, 43, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = "white";
        context.font = "bold 58px sans-serif";
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(entry.text, 48, 50);
      }
      const texture = new THREE.CanvasTexture(canvas);
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: texture, depthTest: false }),
      );
      sprite.position.set(entry.position[0], entry.position[1], 0.1);
      sprite.scale.set(0.08, 0.08, 1);
      group.add(sprite);
      return { sprite, texture };
    });
    return () =>
      markers.forEach(({ sprite, texture }) => {
        group.remove(sprite);
        sprite.material.dispose();
        texture.dispose();
      });
  }, [pickupStart, target]);

  return (
    <div ref={host} className="world" aria-label={t("三维仿真场景")}>
      <div
        className="viewport-tools"
        role="toolbar"
        aria-label={t("三维视角控制")}
      >
        <button
          type="button"
          className="viewport-btn"
          title={t("复位最佳视角")}
          aria-label={t("复位最佳视角")}
          onClick={() => {
            cameraModeRef.current = "free";
            setActiveCameraMode("free");
            fitView.current?.();
          }}
        >
          ⟲ {t("复位")}
        </button>
        <button
          type="button"
          className={`viewport-btn ${activeCameraMode === "follow" ? "active" : ""}`}
          title={t("视角跟随机器人")}
          aria-label={t("视角跟随机器人")}
          onClick={() => {
            const next = activeCameraMode === "follow" ? "free" : "follow";
            cameraModeRef.current = next;
            setActiveCameraMode(next);
          }}
        >
          ⊙ {t("跟随")}
        </button>
        <button
          type="button"
          className={`viewport-btn ${activeCameraMode === "top" ? "active" : ""}`}
          title={t("正上方顶视鸟瞰")}
          aria-label={t("正上方顶视鸟瞰")}
          onClick={() => {
            cameraModeRef.current = "top";
            setActiveCameraMode("top");
            setTopView.current?.();
          }}
        >
          ⊞ {t("顶视")}
        </button>
      </div>

      <div className="viewport-hud" aria-hidden="true">
        <span>X: {(frame?.position?.[0] ?? 0).toFixed(2)}m</span>
        <span>Y: {(frame?.position?.[1] ?? 0).toFixed(2)}m</span>
        <span>Z: {(frame?.position?.[2] ?? 0.29).toFixed(2)}m</span>
        {frame?.t !== undefined && <span>t: {frame.t.toFixed(1)}s</span>}
      </div>

      {unsupported && (
        <div className="webgl-message">
          {t("当前浏览器无法显示 3D。运行记录与评分仍可查看。")}
        </div>
      )}
    </div>
  );
}
