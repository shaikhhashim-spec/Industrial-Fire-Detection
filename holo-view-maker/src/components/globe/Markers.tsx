import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { CATEGORY_COLORS, latLonToVec3, type ThermalEvent } from "@/lib/thermal";
import { planMarkerRender, type Cluster } from "@/lib/marker-clustering";

const GLOBE_R = 2;

/** Camera distance the marker sizes below were tuned at (ThermalGlobe's initial camera position). */
const REFERENCE_CAMERA_DIST = 5.44;
const MIN_MARKER_SCALE = 0.32;
const MAX_MARKER_SCALE = 2.2;

interface BeamProps {
  cluster: Cluster;
  selected: boolean;
  colorBy: "category" | "risk";
  onSelect: (id: string) => void;
}

function Beam({ cluster, selected, colorBy, onSelect }: BeamProps) {
  const group = useRef<THREE.Group>(null);
  const halo = useRef<THREE.Mesh>(null);
  const worldPos = useMemo(() => new THREE.Vector3(), []);

  const { position, quaternion, height, color, size, primary } = useMemo(() => {
    // The highest-risk detection in the cluster drives color/height/selection —
    // it's the one worth an analyst's attention first.
    const lead = cluster.events.reduce((a, b) => (b.riskScore > a.riskScore ? b : a));
    const p = new THREE.Vector3(...latLonToVec3(cluster.latitude, cluster.longitude, GLOBE_R));
    const q = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      p.clone().normalize(),
    );
    const h = 0.05 + (lead.riskScore / 100) * 0.42;
    const c =
      colorBy === "category"
        ? CATEGORY_COLORS[lead.category]
        : lead.riskScore >= 80
          ? "#e66767"
          : lead.riskScore >= 60
            ? "#ec835a"
            : lead.riskScore >= 35
              ? "#fab219"
              : "#0ca30c";
    // Scale markers conservatively with distance so they stay razor-sharp needles rather than ballooning into blobs
    const s = 0.75 + Math.min(0.5, Math.log2(cluster.events.length) * 0.08);
    return { position: p, quaternion: q, height: h, color: c, size: s, primary: lead };
  }, [cluster, colorBy]);

  useFrame((state) => {
    if (group.current) {
      group.current.getWorldPosition(worldPos);
      const dist = state.camera.position.distanceTo(worldPos);
      // Keep pins ultra-fine and crisp; clamp tightly so they never swell into giant blobs
      const scale = THREE.MathUtils.clamp(
        dist / REFERENCE_CAMERA_DIST,
        0.35,
        0.85,
      );
      group.current.scale.setScalar(scale);
    }
    if (!halo.current) return;
    const t = state.clock.elapsedTime * 2.2 + (primary.riskScore * 0.1);
    const pulse = selected ? 1.5 + Math.sin(t * 2) * 0.4 : 1 + Math.sin(t) * 0.22;
    halo.current.scale.setScalar(pulse);
  });

  return (
    <group
      ref={group}
      position={position}
      quaternion={quaternion}
      onClick={(e: { stopPropagation: () => void }) => {
        e.stopPropagation();
        onSelect(primary.id);
      }}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      {/* 1. Outer translucent thermal energy beam */}
      <mesh position={[0, height / 2, 0]}>
        <cylinderGeometry args={[0.0022 * size, 0.0055 * size, height, 8]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={selected ? 0.95 : 0.7}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* 2. Intense white-hot inner laser core */}
      <mesh position={[0, height / 2, 0]}>
        <cylinderGeometry args={[0.0008 * size, 0.0018 * size, height * 1.02, 6]} />
        <meshBasicMaterial
          color="#ffffff"
          transparent
          opacity={selected ? 0.95 : 0.8}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* 3. Luminous apex diamond beacon (replaces giant ball) */}
      <mesh position={[0, height, 0]}>
        <octahedronGeometry args={[(selected ? 0.012 : 0.0085) * size, 0]} />
        <meshBasicMaterial color={color} />
      </mesh>

      {/* 4. Apex glow halo */}
      <mesh position={[0, height, 0]}>
        <sphereGeometry args={[(selected ? 0.018 : 0.013) * size, 8, 8]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={selected ? 0.6 : 0.35}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* 5. Precise ground contact thermal point on Earth terrain */}
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.001, 0]}>
        <circleGeometry args={[0.006 * size, 16]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.85}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* 6. Pulsing ground radar / thermal radiation footprint ring */}
      <mesh ref={halo} rotation-x={-Math.PI / 2} position={[0, 0.002, 0]}>
        <ringGeometry args={[0.01 * size, 0.018 * size, 24]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={selected ? 0.75 : 0.45}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

export function Markers({
  events,
  selectedId,
  colorBy,
  onSelect,
}: {
  events: ThermalEvent[];
  selectedId: string | null;
  colorBy: "category" | "risk";
  onSelect: (id: string) => void;
}) {
  const { visible: clusters } = useMemo(() => planMarkerRender(events), [events]);

  return (
    <group>
      {clusters.map((c) => (
        <Beam
          key={c.key}
          cluster={c}
          selected={c.events.some((e) => e.id === selectedId)}
          colorBy={colorBy}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}
