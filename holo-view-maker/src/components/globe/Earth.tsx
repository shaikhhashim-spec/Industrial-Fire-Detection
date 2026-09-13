import { useTexture } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const R = 2;

/** Direction toward the "sun" — must match the directional light position in ThermalGlobe. */
export const SUN_DIRECTION = new THREE.Vector3(6, 2.5, 4).normalize();

const lightsVertex = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vNormalW;
  void main() {
    vUv = uv;
    vNormalW = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const lightsFragment = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vNormalW;
  uniform sampler2D map;
  uniform vec3 uSunDir;
  uniform float uOpacity;
  void main() {
    float ndotl = dot(vNormalW, uSunDir);
    // Only glow when the sun is below the horizon (night side)
    // ndotl < -0.02 ensures zero bleed onto daylight continents
    float night = clamp((-ndotl - 0.02) * 7.5, 0.0, 1.0);
    vec4 tex = texture2D(map, vUv);
    // Warm luminous city glow
    vec3 cityColor = tex.rgb * vec3(1.2, 0.95, 0.65);
    gl_FragColor = vec4(cityColor, tex.r * night * uOpacity);
  }
`;

/** Photoreal day/night Earth with normal + specular relief and a drifting cloud shell. */
export function Earth() {
  const baseUrl = import.meta.env.BASE_URL;
  const maps = useTexture([
    `${baseUrl}textures/earth_atmos_2048.jpg`,
    `${baseUrl}textures/earth_normal_2048.jpg`,
    `${baseUrl}textures/earth_specular_2048.jpg`,
    `${baseUrl}textures/earth_lights_2048.png`,
    `${baseUrl}textures/earth_clouds_1024.png`,
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
  normal.anisotropy = 4;
  spec.anisotropy = 4;

  const lightsMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: lightsVertex,
        fragmentShader: lightsFragment,
        uniforms: {
          map: { value: lights },
          uSunDir: { value: SUN_DIRECTION },
          uOpacity: { value: 1.4 },
        },
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    [lights],
  );

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
        <sphereGeometry args={[R, 128, 128]} />
        <meshPhongMaterial
          map={day}
          normalMap={normal}
          normalScale={new THREE.Vector2(1.0, 1.0)}
          specularMap={spec}
          specular={new THREE.Color("#4c7a99")}
          shininess={34}
        />
      </mesh>

      {/* city lights, visible only on the night side */}
      <mesh scale={1.001} material={lightsMaterial}>
        <sphereGeometry args={[R, 128, 128]} />
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
          uColor: { value: new THREE.Color("#3b9eff") },
          uPower: { value: 4.2 },
          uStrength: { value: 1.35 },
        },
        transparent: true,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        depthWrite: false,
      }),
    [],
  );

  return (
    <mesh scale={1.025} material={material}>
      <sphereGeometry args={[R, 96, 96]} />
    </mesh>
  );
}
