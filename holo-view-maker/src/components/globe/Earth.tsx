import { useTexture } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const R = 2;

/** Photoreal day/night Earth with normal + specular relief and a drifting cloud shell. */
export function Earth() {
  const maps = useTexture([
    "/textures/earth_atmos_2048.jpg",
    "/textures/earth_normal_2048.jpg",
    "/textures/earth_specular_2048.jpg",
    "/textures/earth_lights_2048.png",
    "/textures/earth_clouds_1024.png",
  ]) as THREE.Texture[];
  const [day, normal, spec, lights, clouds] = maps as [
    THREE.Texture,
    THREE.Texture,
    THREE.Texture,
    THREE.Texture,
    THREE.Texture,
  ];

  day.colorSpace = THREE.SRGBColorSpace;
  lights.colorSpace = THREE.SRGBColorSpace;
  day.anisotropy = 8;


  const cloudRef = useRef<THREE.Mesh>(null);
  useFrame((state, delta) => {
    if (cloudRef.current) {
      cloudRef.current.rotation.y += Math.min(delta, 0.05) * 0.006;
      const camDist = state.camera.position.length();
      const altFactor = Math.max(0, Math.min(1, (camDist - 2.12) / (3.2 - 2.12)));
      (cloudRef.current.material as any).opacity = 0.42 * Math.pow(altFactor, 1.8);
    }
  });

  return (
    <group>
      {/* surface */}
      <mesh>
        <sphereGeometry args={[R, 96, 96]} />
        <meshPhongMaterial
          map={day}
          normalMap={normal}
          normalScale={new THREE.Vector2(0.85, 0.85)}
          specularMap={spec}
          specular={new THREE.Color("#3a5a72")}
          shininess={18}
        />
      </mesh>

      {/* city lights on the dark side */}
      <mesh scale={1.001}>
        <sphereGeometry args={[R, 96, 96]} />
        <meshBasicMaterial
          map={lights}
          blending={THREE.AdditiveBlending}
          transparent
          opacity={0.55}
          depthWrite={false}
        />
      </mesh>

      {/* clouds */}
      <mesh ref={cloudRef} scale={1.012}>
        <sphereGeometry args={[R, 64, 64]} />
        <meshLambertMaterial
          map={clouds}
          transparent
          opacity={0.42}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

const atmosVertex = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

const atmosFragment = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  uniform vec3 uColor;
  uniform float uPower;
  uniform float uStrength;
  void main() {
    float f = pow(1.0 - abs(dot(vNormal, vView)), uPower);
    gl_FragColor = vec4(uColor, f * uStrength);
  }
`;

/** Fresnel rim glow that reads as a real atmospheric limb. */
export function Atmosphere() {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: atmosVertex,
        fragmentShader: atmosFragment,
        uniforms: {
          uColor: { value: new THREE.Color("#5aa9e6") },
          uPower: { value: 3.0 },
          uStrength: { value: 1.15 },
        },
        transparent: true,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        depthWrite: false,
      }),
    [],
  );

  return (
    <mesh scale={1.09} material={material}>
      <sphereGeometry args={[R, 64, 64]} />
    </mesh>
  );
}
