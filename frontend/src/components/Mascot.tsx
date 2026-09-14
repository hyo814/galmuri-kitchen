/** 요리사 모자를 쓴 다람이(AILoading 시안의 SVG). 꾸밈이라 스크린리더에는 읽히지 않는다. */
export default function Mascot({ size = 72 }: { size?: number }) {
  return (
    <svg className="rc-empty-mark" width={size} height={size} viewBox="0 0 512 512" aria-hidden="true">
      <rect width="512" height="512" rx="115" fill="#0b7a4c" />
      <g transform="translate(256 256) scale(0.78) translate(-286 -240)">
        <path d="M330 382 C440 374 462 262 414 218 C384 190 390 146 434 136" fill="none" stroke="#ffffff" strokeWidth="68" strokeLinecap="round" />
        <path d="M168 360 H304 L252 426 Q236 444 220 426 Z" fill="#ffc94a" />
        <path
          d="M236 186 C300 186 346 214 354 262 C358 288 366 306 382 326 C360 330 346 330 336 334 C322 360 280 386 236 386 C192 386 150 360 136 334 C126 330 112 330 90 326 C106 306 114 288 118 262 C126 214 172 186 236 186 Z"
          fill="#ffffff"
          stroke="#0b7a4c"
          strokeWidth="16"
          strokeLinejoin="round"
          paintOrder="stroke"
        />
        <path d="M130 250 C112 206 98 160 84 94 L104 116 L110 88 C142 126 176 168 196 206 Z" fill="#ffffff" />
        <path d="M342 250 C360 206 374 160 388 94 L368 116 L362 88 C330 126 296 168 276 206 Z" fill="#ffffff" />
        <path d="M138 228 C128 198 118 170 110 140 C134 162 156 186 172 212 Z" fill="#ffc94a" />
        <path d="M334 228 C344 198 354 170 362 140 C338 162 316 186 300 212 Z" fill="#ffc94a" />
        <path d="M176 284 Q194 266 212 284" fill="none" stroke="#07140d" strokeWidth="11" strokeLinecap="round" strokeLinejoin="round" />
        <ellipse cx="278" cy="282" rx="17" ry="21" fill="#07140d" />
        <circle cx="284" cy="273" r="6" fill="#ffffff" />
        <path d="M258 246 Q282 232 304 244" fill="none" stroke="#07140d" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M222 312 H250 Q256 312 252 318 L240 330 Q236 334 232 330 L220 318 Q216 312 222 312 Z" fill="#07140d" />
        <rect x="224" y="344" width="24" height="22" rx="5" fill="#ffffff" stroke="#07140d" strokeWidth="6" />
        <path d="M236 346 V364" stroke="#07140d" strokeWidth="5" />
        <path d="M208 336 Q236 354 266 332" fill="none" stroke="#07140d" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <g transform="rotate(-9 236 196) translate(236 196) scale(.82) translate(-236 -196)">
          <path
            d="M170 174 L162 112 C126 104 124 50 168 44 C178 8 222 0 236 24 C250 0 294 8 304 44 C348 50 346 104 310 112 L302 174 Z"
            fill="#ffffff"
            stroke="#0b7a4c"
            strokeWidth="20"
            strokeLinejoin="round"
            paintOrder="stroke"
          />
          <path d="M204 118 V160" stroke="#0b7a4c" strokeWidth="10" strokeLinecap="round" />
          <path d="M236 100 V160" stroke="#0b7a4c" strokeWidth="10" strokeLinecap="round" />
          <path d="M268 118 V160" stroke="#0b7a4c" strokeWidth="10" strokeLinecap="round" />
          <rect x="158" y="166" width="156" height="48" rx="14" fill="#ffffff" stroke="#0b7a4c" strokeWidth="20" paintOrder="stroke" />
        </g>
      </g>
    </svg>
  );
}
