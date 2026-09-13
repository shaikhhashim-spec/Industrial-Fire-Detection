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
    // count===1 -> 1x (identical to a single un-clustered marker), grows with
    // log(count) so a 200-detection corridor reads as a bigger point, not 200
    // stacked copies of the same-size marker.
    const s = 1 + Math.min(1.2, Math.log2(cluster.events.length) * 0.22);
    return { position: p, quaternion: q, height: h, color: c, size: s, primary: lead };
  }, [cluster, colorBy]);

  useFrame((state) => {
    // Keep markers a consistent, legible size on screen regardless of zoom —
    // without this, zooming into a tight cluster of events (all at roughly
    // the same real-world size) makes their halos balloon into one solid blob.
    if (group.current) {
      group.current.getWorldPosition(worldPos);
      const dist = state.camera.position.distanceTo(worldPos);
      const scale = THREE.MathUtils.clamp(
        dist / REFERENCE_CAMERA_DIST,
        MIN_MARKER_SCALE,
        MAX_MARKER_SCALE,
      );
      group.current.scale.setScalar(scale);
    }
    if (!halo.current) return;
    const t = state.clock.elapsedTime * 1.4 + primary.riskScore;
    const pulse = selected ? 1.4 + Math.sin(t * 2) * 0.35 : 1 + Math.sin(t) * 0.15;
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
      <mesh position={[0, height / 2, 0]}>
        <cylinderGeometry args={[0.008 * size, 0.016 * size, height, 12]} />
        <meshBasicMaterial color={color} transparent opacity={selected ? 1 : 0.88} />
      </mesh>
      <mesh position={[0, height, 0]}>
        <sphereGeometry args={[(selected ? 0.035 : 0.028) * size, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh position={[0, height * 0.5, 0]}>
        <sphereGeometry args={[0.018 * size, 12, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {/* Small, tight-to-the-base glow ring — kept close to the beam so dense
          clusters of nearby events read as distinct points, not a merged blob. */}
      <mesh ref={halo} rotation-x={-Math.PI / 2} position={[0, 0.004, 0]}>
        <ringGeometry args={[0.02 * size, 0.032 * size, 32]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={selected ? 0.55 : 0.35}
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
