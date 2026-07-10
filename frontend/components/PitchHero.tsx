"use client";

import { useEffect, useState } from "react";

// Ilustração animada do campo (hero): jogador piscando, trajetória fluindo,
// heatmap pulsando e a velocidade mudando sozinha — dá vida à página.
export default function PitchHero() {
  const [spd, setSpd] = useState("28 km/h");

  useEffect(() => {
    const vals = ["28 km/h", "31 km/h", "27 km/h", "33 km/h", "29 km/h", "25 km/h"];
    let i = 0;
    const id = setInterval(() => {
      i = (i + 1) % vals.length;
      setSpd(vals[i]);
    }, 950);
    return () => clearInterval(id);
  }, []);

  return (
    <svg viewBox="0 0 340 230" width="100%" role="img" aria-label="Campo de futebol com jogadores rastreados.">
      <rect x="8" y="8" width="324" height="214" rx="12" fill="#166534" />
      <ellipse className="fe-heat" cx="112" cy="152" rx="30" ry="20" fill="#f97316" />
      <rect x="8" y="8" width="324" height="214" rx="12" fill="none" stroke="#bbf7d0" strokeWidth="2" />
      <line x1="170" y1="8" x2="170" y2="222" stroke="#bbf7d0" strokeWidth="2" />
      <circle cx="170" cy="115" r="30" fill="none" stroke="#bbf7d0" strokeWidth="2" />
      <circle cx="170" cy="115" r="3" fill="#bbf7d0" />
      <rect x="8" y="72" width="46" height="86" fill="none" stroke="#bbf7d0" strokeWidth="2" />
      <rect x="286" y="72" width="46" height="86" fill="none" stroke="#bbf7d0" strokeWidth="2" />
      <polyline className="fe-traj" points="128,96 170,115 214,138 268,158" fill="none" stroke="#ffffff" strokeWidth="2" />
      <circle className="fe-pulse" cx="72" cy="62" r="6" fill="#ffffff" />
      <rect className="fe-pulse" x="63" y="51" width="18" height="24" fill="none" stroke="#34a05f" strokeWidth="1.8" />
      <circle cx="112" cy="152" r="6" fill="#ffffff" />
      <circle cx="128" cy="96" r="6" fill="#ffffff" />
      <circle cx="238" cy="70" r="6" fill="#0a0a0a" />
      <circle cx="268" cy="158" r="6" fill="#0a0a0a" />
      <circle cx="214" cy="138" r="6" fill="#0a0a0a" />
      <rect x="57" y="37" width="56" height="15" rx="4" fill="#0a0a0a" />
      <text x="63" y="48" fill="#4ade80" fontSize="10">{spd}</text>
    </svg>
  );
}
