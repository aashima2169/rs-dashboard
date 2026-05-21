import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Nav }       from './components/Nav'
import Dashboard     from './pages/Dashboard'
import Screener      from './pages/Screener'

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/"          element={<Dashboard />} />
        <Route path="/screener"  element={<Screener />} />
      </Routes>
    </BrowserRouter>
  )
}
