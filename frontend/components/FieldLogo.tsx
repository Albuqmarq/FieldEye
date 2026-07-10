// Logo do FieldEye: um campo de futebol com a bola central envolta por um
// contorno de olho (Field + Eye). Recebe tamanho e cor do traço.
export default function FieldLogo({
  size = 34,
  stroke = "#34a05f",
}: {
  size?: number;
  stroke?: string;
}) {
  const height = Math.round((size * 30) / 44);
  return (
    <svg viewBox="0 0 44 30" width={size} height={height} aria-hidden="true">
      <rect x="2" y="2" width="40" height="26" rx="4" fill="none" stroke={stroke} strokeWidth="1.6" />
      <line x1="22" y1="2" x2="22" y2="28" stroke={stroke} strokeWidth="1.2" />
      <rect x="2" y="9" width="7" height="12" fill="none" stroke={stroke} strokeWidth="1.2" />
      <rect x="35" y="9" width="7" height="12" fill="none" stroke={stroke} strokeWidth="1.2" />
      <path d="M12 15 Q22 6 32 15 Q22 24 12 15 Z" fill="none" stroke={stroke} strokeWidth="1.4" />
      <circle cx="22" cy="15" r="4" fill={stroke} />
    </svg>
  );
}
