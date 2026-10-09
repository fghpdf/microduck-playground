export interface Terrain {
  kind: "ramp";
  position: [number, number, number];
  size: [number, number, number];
  direction: 1 | -1;
}
export interface Obstacle {
  position: [number, number, number];
  size: [number, number, number];
  yaw: number;
}
export interface SceneObject {
  quaternion?: [number, number, number, number];
  id: string;
  kind: "ball" | "trash";
  position: [number, number, number];
  radius?: number;
  size?: [number, number, number];
}
export interface Goal {
  x: number;
  y: number;
  width: number;
}
export interface Task {
  kind: "football" | "pickup" | "navigation";
  skill?: "kick_left" | "kick_right" | "ground_pick";
}
export interface Scenario {
  fast_only?: boolean;
  task_type?: "football" | "pickup" | "navigation";
  skill?: "kick_left" | "kick_right" | "ground_pick";
  objects?: SceneObject[];
  goal?: Goal;
  difficulty?: "simple" | "advanced" | "complex";
  category?: "navigation" | "obstacle" | "terrain" | "football" | "pickup";
  obstacles?: Obstacle[];
  terrain?: Terrain[];
  id: string;
  name: string;
  description: string;
  target: [number, number];
  duration: number;
}
export interface Frame {
  t: number;
  position: [number, number, number];
  quaternion: [number, number, number, number];
  joints: number[];
  ball?: [number, number, number];
  objects?: SceneObject[];
  pickup?: {
    phase?: string;
    attached?: boolean;
    released?: boolean;
    grasp_model?: string;
  };
}
export interface RunDiagnostics {
  commands: {
    sent_at: number;
    duration_ms: number;
    vx: number;
    vyaw: number;
    accepted: boolean | null;
    error: string | null;
  }[];
  health: {
    sampled_at: number;
    duration_ms: number;
    result: null | {
      healthy?: boolean;
      reason?: string | null;
      control_loop?: { target_hz?: number; achieved_hz?: number | null };
    };
    error: string | null;
  }[];
}
export interface Run {
  task_type?: "football" | "pickup" | "navigation";
  skill?: "kick_left" | "kick_right" | "ground_pick";
  objects?: SceneObject[];
  goal?: Goal;
  scenario_snapshot?: Scenario;
  difficulty?: Scenario["difficulty"];
  category?: Scenario["category"];
  obstacles?: Obstacle[];
  terrain?: Terrain[];
  mode?: "realtime" | "fast_reference";
  wall_duration?: number;
  target?: [number, number];
  start_pose?: {
    position: [number, number, number];
    quaternion: [number, number, number, number];
  };
  id: string;
  scenario_id: string;
  status: string;
  frames?: Frame[];
  events?: unknown[];
  error?: string;
  diagnostics?: RunDiagnostics;
  score?: null | {
    success: boolean;
    completion: number;
    duration: number;
    falls: number;
    collisions: number;
    details?: Record<string, unknown>;
  };
}
export async function request<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(
    url,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `请求失败（${response.status}）`,
    );
  }
  return response.json();
}
