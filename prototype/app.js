const sections = {
  dashboard: 'OEE онлайн',
  production: 'Производство',
  downtime: 'Простои',
  quality: 'ГП / Брак / ОТК',
  reconciliation: 'Сверка источников',
  payroll: 'Сдельная заработная плата',
  imports: 'Импорт данных'
};

const shiftData = {
  day: {
    label: 'ДЕНЬ · 09:00–21:00',
    oee: 76.4, availability: 88.2, performance: 91.5, quality: 94.7,
    plan: 82000, fact: 61450, gp: 59870, scrap: 1580, downtime: '01:24', downtimeCount: 6, active: 1,
    recon: [61450,59920,59870,58900],
    machines: [
      ['ПДМ-01','Пакет 320×200',82,'РАБОТАЕТ','running'],
      ['ПДМ-02','Пакет 280×180',68,'ПРОСТОЙ 00:17:42','stop'],
      ['ПДМ-03','Пакет 350×260',79,'РАБОТАЕТ','running'],
      ['ПДМ-04','Пакет 240×140',74,'РАБОТАЕТ','running']
    ],
    chart: [[64,57],[70,66],[76,70],[80,74],[84,78],[88,83],[91,87],[95,90],[98,92],[100,96]]
  },
  night: {
    label: 'НОЧЬ · 21:00–09:00 следующего дня',
    oee: 71.8, availability: 84.7, performance: 90.1, quality: 94.0,
    plan: 76000, fact: 53200, gp: 51840, scrap: 1360, downtime: '01:51', downtimeCount: 8, active: 0,
    recon: [53200,51870,51840,51840],
    machines: [
      ['ПДМ-01','Пакет 320×200',75,'РАБОТАЕТ','running'],
      ['ПДМ-02','Пакет 280×180',72,'РАБОТАЕТ','running'],
      ['ПДМ-03','Пакет 350×260',69,'РАБОТАЕТ','running'],
      ['ПДМ-04','Пакет 240×140',70,'ПЕРЕНАЛАДКА','stop']
    ],
    chart: [[60,51],[65,58],[72,62],[76,68],[81,73],[85,75],[89,81],[93,84],[97,88],[100,91]]
  }
};

function formatNumber(n){ return new Intl.NumberFormat('ru-RU').format(n); }

function setSection(id){
  document.querySelectorAll('.content-section').forEach(el => el.classList.toggle('active', el.id === id));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.section === id));
  document.getElementById('pageTitle').textContent = sections[id] || 'VITAGROUP';
  document.getElementById('sidebar').classList.remove('open');
  window.scrollTo({top:0,behavior:'smooth'});
}

function renderMachines(items){
  const root = document.getElementById('machineList');
  root.innerHTML = items.map(m => '<div class="machine"><div class="machine-name"><strong>'+m[0]+'</strong><small>'+m[1]+'</small></div><div class="machine-meter"><span style="width:'+m[2]+'%"></span></div><div class="machine-status '+m[4]+'">'+m[3]+'<br><small>OEE '+m[2]+'%</small></div></div>').join('');
}

function renderChart(values){
  const root = document.getElementById('hourChart');
  root.innerHTML = values.map(v => '<div class="bar-pair"><div class="bar plan" style="height:'+v[0]+'%"></div><div class="bar fact" style="height:'+v[1]+'%"></div></div>').join('');
}

function applyShift(key){
  const d = shiftData[key];
  document.querySelectorAll('.segment').forEach(el => el.classList.toggle('active', el.dataset.shift === key));
  document.getElementById('shiftLabel').textContent = d.label;
  document.getElementById('oeeValue').textContent = d.oee.toFixed(1).replace('.',',')+'%';
  document.getElementById('availabilityValue').textContent = d.availability.toFixed(1).replace('.',',')+'%';
  document.getElementById('performanceValue').textContent = d.performance.toFixed(1).replace('.',',')+'%';
  document.getElementById('qualityValue').textContent = d.quality.toFixed(1).replace('.',',')+'%';
  document.getElementById('oeeDonut').style.setProperty('--value', d.oee);
  document.getElementById('planValue').textContent = formatNumber(d.plan);
  document.getElementById('factValue').textContent = formatNumber(d.fact);
  document.getElementById('gpValue').textContent = formatNumber(d.gp);
  document.getElementById('scrapValue').textContent = formatNumber(d.scrap);
  const pct = d.fact/d.plan*100;
  document.getElementById('planPercent').textContent = pct.toFixed(1).replace('.',',')+'%';
  document.getElementById('planProgress').style.width = Math.min(pct,100)+'%';
  document.getElementById('downtimeValue').textContent = d.downtime;
  document.getElementById('downtimeCount').textContent = d.downtimeCount;
  document.getElementById('activeDowntime').textContent = d.active;
  const ids = ['reconOperator','reconQc','reconWarehouse','reconErp'];
  ids.forEach((id,i) => document.getElementById(id).textContent = formatNumber(d.recon[i]));
  document.getElementById('erpDelta').textContent = formatNumber(Math.abs(d.recon[2]-d.recon[3]))+' шт.';
  renderMachines(d.machines);
  renderChart(d.chart);
}

document.querySelectorAll('.nav-item').forEach(btn => btn.addEventListener('click', () => setSection(btn.dataset.section)));
document.querySelectorAll('[data-go]').forEach(btn => btn.addEventListener('click', () => setSection(btn.dataset.go)));
document.querySelectorAll('.segment').forEach(btn => btn.addEventListener('click', () => applyShift(btn.dataset.shift)));
document.getElementById('mobileMenu').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));

applyShift('day');
