function currentTheme(){
  return localStorage.getItem('clinicdesk-theme') || 'dark';
}

function applyTheme(theme){
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('clinicdesk-theme', theme);
  const button = document.getElementById('theme');
  if(button){
    button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    button.title = theme === 'dark' ? 'Light mode' : 'Dark mode';
  }
}

function initTheme(){
  applyTheme(currentTheme());
  const button = document.getElementById('theme');
  if(button){
    button.onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  }
}

document.documentElement.dataset.theme = currentTheme();
document.addEventListener('DOMContentLoaded', initTheme);
