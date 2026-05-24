import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import App from './App';
import WikiPage from './pages/Wiki';
import OraclePage from './pages/Oracle';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<Navigate to="/wiki" replace />} />
          <Route path="/wiki" element={<WikiPage />} />
          <Route path="/wiki/:type/:slug" element={<WikiPage />} />
          <Route path="/oracle" element={<OraclePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
