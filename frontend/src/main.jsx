import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { BusinessProvider } from './context/BusinessContext.jsx'
import Overview from './pages/Overview.jsx'
import ReviewFeed from './pages/ReviewFeed.jsx'
import Competitors from './pages/Competitors.jsx'
import Trends from './pages/Trends.jsx'
import Chatbot from './pages/Chatbot.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <BusinessProvider>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<Overview />} />
            <Route path="reviews" element={<ReviewFeed />} />
            <Route path="competitors" element={<Competitors />} />
            <Route path="trends" element={<Trends />} />
            <Route path="chatbot" element={<Chatbot />} />
          </Route>
        </Routes>
      </BusinessProvider>
    </BrowserRouter>
  </StrictMode>,
)
