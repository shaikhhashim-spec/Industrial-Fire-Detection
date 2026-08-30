import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { CATEGORY_COLORS, latLonToVec3, type ThermalEvent } from "@/lib/thermal";

const GLOBE_R = 2;

function Beam({
  event,
  selected,
  colorBy,
  onSelect,
}: {
  event: ThermalEvent;
  selected: boolean;
  colorBy: "category" | "risk";
  onSelect: (id: string) => void;
}) {
  const group = useRef<THREE.Group>(null);
  const halo = useRef<THREE.Mesh>(null);

  const { position, quaternion, height, color } = useMemo(() => {
    const p = new THREE.Vector3(...latLonToVec3(event.latitude, event.longitude, GLOBE_R));
    const q = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      p.clone().normalize(),
    );
    const h = 0.05 + (event.riskScore / 100) * 0.42;
    const c =
      colorBy === "category"
        ? CATEGORY_COLORS[event.category]
        : event.riskScore >= 80
          ? "#e66767"
          : event.riskScore >= 60
            ? "#ec835a"
            : event.riskScore >= 35
              ? "#fab219"
              : "#0ca30c";
    return { position: p, quaternion: q, height: h, color: c };
  }, [event, colorBy]);

  useFrame((state) => {
    if (!halo.current) return;
    const t = state.clock.elapsedTime * 1.4 + event.riskScore;
    const pulse = selected ? 1.4 + Math.sin(t * 2) * 0.35 : 1 + Math.sin(t) * 0.15;
    halo.current.scale.setScalar(pulse);
  });

  return (
    <group
      ref={group}
      position={position}
      quaternion={quaternion}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(event.id);
      }}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      <mesh position={[0, height / 2, 0]}>
        <cylinderGeometry args={[0.004, 0.01, height, 6]} />
        <meshBasicMaterial color={color} transparent opacity={selected ? 1 : 0.85} />
      </mesh>
      <mesh position={[0, height, 0]}>
        <sphereGeometry args={[selected ? 0.035 : 0.022, 12, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh ref={halo} rotation-x={-Math.PI / 2} position={[0, 0.004, 0]}>
        <ringGeometry args={[0.03, 0.055, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
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
  return (
    <group>
      {events.map((e) => (
        <Beam
          key={e.id}
          event={e}
          selected={e.id === selectedId}
          colorBy={colorBy}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}
