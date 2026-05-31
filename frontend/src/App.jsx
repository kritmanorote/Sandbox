import { useState, useEffect } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from './assets/vite.svg'
import heroImg from './assets/hero.png'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [backendStatus, setBackendStatus] = useState('checking...')
  const [leaderboard, setLeaderboard] = useState([])

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => res.json())
      .then((data) => setBackendStatus(`Backend: ${data.status} | DB: ${data.db ?? 'not connected'}`))
      .catch(() => setBackendStatus('Backend: unreachable'))

    fetch(`${API_URL}/leaderboard`)
      .then((res) => res.json())
      .then(setLeaderboard)
      .catch(() => {})
  }, [])

  const gameUrl = `/neonDash/index.html?api=${encodeURIComponent(API_URL)}`
  const chatUrl = `/chat/index.html?api=${encodeURIComponent(API_URL)}`

  return (
    <>
      <section id="center">
        <div className="hero">
          <img src={heroImg} className="base" width="170" height="179" alt="" />
          <img src={reactLogo} className="framework" alt="React logo" />
          <img src={viteLogo} className="vite" alt="Vite logo" />
        </div>
        <div>
          <h1>Neon Dash</h1>
          <p><strong>{backendStatus}</strong></p>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center' }}>
            <a href={gameUrl} target="_blank" rel="noopener noreferrer">
              <button type="button" className="counter">Play Neon Dash</button>
            </a>
            <a href="/pacman/index.html" target="_blank" rel="noopener noreferrer">
              <button type="button" className="counter">Play Pacman</button>
            </a>
            <a href={chatUrl} target="_blank" rel="noopener noreferrer">
              <button type="button" className="counter">Open Chat</button>
            </a>
          </div>
        </div>
      </section>

      <div className="ticks"></div>

      <section id="next-steps">
        <div id="docs">
          <svg className="icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#documentation-icon"></use>
          </svg>
          <h2>Leaderboard</h2>
          <p>Top 5 scores</p>
          {leaderboard.length === 0 ? (
            <p style={{ color: '#888', marginTop: '12px', fontFamily: 'monospace' }}>No scores yet. Be the first!</p>
          ) : (
            <ol style={{ marginTop: '12px', paddingLeft: '1.2em' }}>
              {leaderboard.map((entry, i) => (
                <li key={i} style={{
                  fontFamily: 'monospace',
                  fontWeight: i === 0 ? 'bold' : 'normal',
                  color: i === 0 ? '#c026d3' : '#0891b2',
                  marginBottom: '6px',
                  fontSize: i === 0 ? '1.05em' : '1em'
                }}>
                  {entry.name} — {entry.score}
                </li>
              ))}
            </ol>
          )}
        </div>
        <div id="social">
          <svg className="icon" role="presentation" aria-hidden="true">
            <use href="/icons.svg#social-icon"></use>
          </svg>
          <h2>Connect with us</h2>
          <p>Join the Vite community</p>
          <ul>
            <li>
              <a href="https://github.com/vitejs/vite" target="_blank">
                <svg className="button-icon" role="presentation" aria-hidden="true">
                  <use href="/icons.svg#github-icon"></use>
                </svg>
                GitHub
              </a>
            </li>
            <li>
              <a href="https://chat.vite.dev/" target="_blank">
                <svg className="button-icon" role="presentation" aria-hidden="true">
                  <use href="/icons.svg#discord-icon"></use>
                </svg>
                Discord
              </a>
            </li>
          </ul>
        </div>
      </section>

      <div className="ticks"></div>
      <section id="spacer"></section>
    </>
  )
}

export default App
