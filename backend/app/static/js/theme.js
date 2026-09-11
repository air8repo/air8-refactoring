// 主题切换功能
function setTheme(theme) {
  // 设置HTML属性
  document.documentElement.setAttribute('data-theme', theme);
  
  // 保存到localStorage
  localStorage.setItem('theme', theme);
  
  // 更新主题图标
  updateThemeIcon(theme);
  
  // 触发主题变化事件
  document.dispatchEvent(new CustomEvent('theme-change'));
}

// 更新主题图标
function updateThemeIcon(theme) {
  const themeIcon = document.getElementById('theme-icon');
  if (theme === 'dark') {
    themeIcon.className = 'fa fa-sun-o';
  } else {
    themeIcon.className = 'fa fa-moon-o';
  }
}

// 初始化主题
function initTheme() {
  // 检查localStorage中的主题设置
  const savedTheme = localStorage.getItem('theme');
  
  // 如果没有保存的主题，使用系统主题
  if (!savedTheme) {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = prefersDark ? 'dark' : 'light';
    setTheme(theme);
  } else {
    setTheme(savedTheme);
  }
}

// 监听系统主题变化
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
  const savedTheme = localStorage.getItem('theme');
  if (!savedTheme) {
    const theme = e.matches ? 'dark' : 'light';
    setTheme(theme);
  }
});

// 页面加载时初始化主题
document.addEventListener('DOMContentLoaded', initTheme);

// 主题切换按钮点击事件
document.addEventListener('click', (e) => {
  // 点击主题切换下拉菜单项
  if (e.target.matches('.dropdown-item[data-theme]')) {
    e.preventDefault();
    const theme = e.target.getAttribute('data-theme');
    setTheme(theme);
  }
});