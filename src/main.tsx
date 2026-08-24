import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import { ErrorBoundary } from './components/ErrorBoundary';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root 엘리먼트를 찾을 수 없습니다.');

createRoot(root).render(
  <StrictMode>
    {/*
      마지막 그물. App 안쪽에도 그물이 둘 있지만(지도·층별 화면) 그 바깥 — 검색창·지역
      고르기·머리말에서 터지면 받아 줄 것이 없어 화면이 통째로 하얘진다.
      ⚠️ 여기가 발동하면 화면 전체가 안내로 바뀐다. 그래도 아무 말 없는 흰 화면보다 낫고,
         무엇보다 **그런 일이 있었다는 사실이 창고에 남는다**(서버가 없어 다른 길이 없다).
    */}
    <ErrorBoundary area="앱 전체" outermost>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
