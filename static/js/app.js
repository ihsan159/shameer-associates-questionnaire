/**
 * SHAMEER ASSOCIATES — PREMIUM DIGITAL RESIDENTIAL DESIGN JOURNEY
 * Frontend Application Engine (Phase 1)
 */

(function () {
  'use strict';

  class ShameerApp {
    constructor() {
      this.schema = null;
      this.visuals = null;
      this.sessionToken = null;
      this.sessionData = {
        answers: {},
        family_members: [],
        dynamic_rooms: [],
        selected_visuals: {},
        uploads: [],
        consultation: null
      };

      this.currentScreen = 'welcome'; // 'welcome', 'philosophy', 'chapter-X', 'review', 'success'
      this.currentChapterIndex = 0; // 0 to 7 (Chapters 1 to 8)
      this.saveDebounceTimer = null;
      this.activeLightboxData = null;

      this.init();
    }

    async init() {
      // 1. Parse Token — check /questionnaire/<token> path first (canonical client link)
      const pathMatch = window.location.pathname.match(/^\/questionnaire\/([a-zA-Z0-9\-]+)$/);
      const urlParams = new URLSearchParams(window.location.search);
      const urlToken = urlParams.get('token');
      const storedToken = localStorage.getItem('sa_questionnaire_token');
      this.sessionToken = (pathMatch ? pathMatch[1] : null) || urlToken || storedToken || null;

      // 2. Fetch Schema and Visuals
      try {
        const [schemaRes, visualsRes] = await Promise.all([
          fetch('/api/schema'),
          fetch('/api/visuals')
        ]);
        this.schema = await schemaRes.json();
        this.visuals = await visualsRes.json();

        // 3. Initialize or Load Session
        if (this.sessionToken) {
          await this.loadSession(this.sessionToken);
        } else {
          await this.createNewSession();
        }

        // 4. Register Global Keyboard Shortcuts (Escape for Lightbox/Modals)
        document.addEventListener('keydown', (e) => {
          if (e.key === 'Escape') {
            this.closeGlobalLightbox();
            this.closeLightbox();
            this.closeTooltip();
            this.closeSaveModal();
          }
        });

        // 5. Render Initial Screen
        if (this.sessionData.status === 'submitted') {
          this.currentScreen = 'success';
          this.render();
        } else if (urlToken || (storedToken && Object.keys(this.sessionData.answers).length > 2)) {
          // If returning client, go directly to their last chapter or chapter 0
          this.currentChapterIndex = this.sessionData.current_chapter || 0;
          this.currentScreen = `chapter-${this.currentChapterIndex}`;
          this.render();
        } else {
          this.currentScreen = 'welcome';
          this.render();
        }

      } catch (err) {
        console.error('Initialization error:', err);
        document.getElementById('app-root').innerHTML = `
          <div class="text-center py-20">
            <h2 class="font-serif text-2xl font-bold text-red-600 mb-2">Connection Error</h2>
            <p class="text-sm text-brand-muted mb-4">Unable to load the design questionnaire. Please check your connection and retry.</p>
            <button onclick="window.location.reload()" class="px-6 py-2 bg-brand-black text-white text-xs font-semibold uppercase tracking-wider rounded">
              Retry
            </button>
          </div>
        `;
      }
    }

    async createNewSession() {
      try {
        const res = await fetch('/api/session/new', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.success && data.token) {
          this.sessionToken = data.token;
          localStorage.setItem('sa_questionnaire_token', this.sessionToken);
          this.sessionData = data.session || this.sessionData;
          this.updateUrlToken();
        }
      } catch (err) {
        console.error('Error creating new session:', err);
      }
    }

    async loadSession(token) {
      try {
        const res = await fetch(`/api/session/${token}`);
        const data = await res.json();
        if (data.success && data.session) {
          this.sessionToken = token;
          this.sessionData = data.session;
          localStorage.setItem('sa_questionnaire_token', token);
          this.updateUrlToken();
        }
      } catch (err) {
        console.error('Error loading session:', err);
      }
    }

    updateUrlToken() {
      if (this.sessionToken && window.history.replaceState) {
        const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname + '?token=' + this.sessionToken;
        window.history.replaceState({ path: newUrl }, '', newUrl);
      }
      const resumeInput = document.getElementById('resume-link-input');
      if (resumeInput) {
        resumeInput.value = window.location.href;
      }
    }

    // ========================================================
    // AUTO-SAVE ENGINE
    // ========================================================
    scheduleAutoSave() {
      this.updateSaveStatus('Saving changes...');
      clearTimeout(this.saveDebounceTimer);
      this.saveDebounceTimer = setTimeout(() => {
        this.performAutoSave();
      }, 400);
    }

    async performAutoSave() {
      if (!this.sessionToken) return;
      try {
        const progress = this.calculateProgress();
        const res = await fetch(`/api/session/${this.sessionToken}/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            answers: this.sessionData.answers,
            current_chapter: this.currentChapterIndex,
            progress_percent: progress
          })
        });
        const data = await res.json();
        if (data.success) {
          this.updateSaveStatus('All changes saved');
          this.updateHeaderProgress();
        } else {
          this.updateSaveStatus('Save error. Retrying...', true);
        }
      } catch (err) {
        console.warn('Autosave failed, retrying in background...', err);
        this.updateSaveStatus('Save error. Retrying...', true);
      }
    }

    updateSaveStatus(text, isError = false) {
      const statusText = document.getElementById('save-status-text');
      const badge = document.getElementById('save-status-badge');
      if (statusText) statusText.textContent = text;
      if (badge) {
        badge.classList.remove('hidden');
        if (isError) {
          badge.classList.add('text-amber-700', 'border-amber-300');
          badge.classList.remove('text-brand-muted', 'border-brand-border');
        } else {
          badge.classList.remove('text-amber-700', 'border-amber-300');
          badge.classList.add('text-brand-muted', 'border-brand-border');
        }
      }
    }

    // ========================================================
    // SCROLL LOCK SYSTEM
    // ========================================================
    lockBodyScroll() {
      document.body.style.overflow = 'hidden';
    }

    unlockBodyScroll() {
      const m1 = document.getElementById('lightbox-modal');
      const m2 = document.getElementById('global-image-lightbox');
      const m3 = document.getElementById('tooltip-modal');
      const m4 = document.getElementById('save-modal');
      const anyOpen = (m1 && !m1.classList.contains('hidden')) ||
                      (m2 && !m2.classList.contains('hidden')) ||
                      (m3 && !m3.classList.contains('hidden')) ||
                      (m4 && !m4.classList.contains('hidden'));
      if (!anyOpen) {
        document.body.style.overflow = '';
      }
    }

    // ========================================================
    // PROGRESS CALCULATION (One source of truth, chapter-based)
    // ========================================================
    calculateProgress() {
      if (!this.schema || !this.schema.chapters) return 0;
      const totalChapters = this.schema.chapters.length; // 8

      if (this.currentScreen === 'success' || this.currentScreen === 'review') return 100;
      if (!this.currentScreen.startsWith('chapter-')) return 0;

      // Chapter 0 (Ch 1) → 13%, Chapter 1 (Ch 2) → 25%, ..., Chapter 7 (Ch 8) → 100%
      return Math.round(((this.currentChapterIndex + 1) / totalChapters) * 100);
    }

    updateHeaderProgress() {
      const progress = this.calculateProgress();
      const progressContainer = document.getElementById('header-progress-container');
      const headerTitle = document.getElementById('header-chapter-title');
      const headerText = document.getElementById('header-progress-text');
      const headerBar = document.getElementById('header-progress-bar');
      const mobileBar = document.getElementById('mobile-progress-bar');

      if (this.currentScreen.startsWith('chapter-') || this.currentScreen === 'review') {
        if (progressContainer) progressContainer.classList.remove('hidden');
        const chNum = this.currentScreen === 'review' ? 8 : this.currentChapterIndex + 1;
        const chTitle = this.currentScreen === 'review' ? 'Brief Review' : this.schema.chapters[this.currentChapterIndex].title;

        if (headerTitle) headerTitle.textContent = `${this.currentScreen === 'review' ? '08' : this.schema.chapters[this.currentChapterIndex].number} ${chTitle}`;
        if (headerText) headerText.textContent = `Chapter ${chNum} of 8 • ${progress}% Complete`;
        if (headerBar) headerBar.style.width = `${progress}%`;
        if (mobileBar) mobileBar.style.width = `${progress}%`;
      } else {
        if (progressContainer) progressContainer.classList.add('hidden');
        if (mobileBar) mobileBar.style.width = '0%';
      }
    }

    // ========================================================
    // NAVIGATION & ROUTING
    // ========================================================
    goToWelcome(e) {
      if (e) e.preventDefault();
      this.currentScreen = 'welcome';
      this.render();
    }

    goToPhilosophy() {
      this.currentScreen = 'philosophy';
      this.render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    startQuestionnaire() {
      this.currentChapterIndex = 0;
      this.currentScreen = 'chapter-0';
      this.render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    goToChapter(index) {
      if (index >= 0 && index < this.schema.chapters.length) {
        this.currentChapterIndex = index;
        this.currentScreen = `chapter-${index}`;
        this.render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }

    nextChapter() {
      this.performAutoSave();
      if (this.currentChapterIndex < this.schema.chapters.length - 1) {
        this.goToChapter(this.currentChapterIndex + 1);
      } else {
        this.goToReview();
      }
    }

    prevChapter() {
      this.performAutoSave();
      if (this.currentChapterIndex > 0) {
        this.goToChapter(this.currentChapterIndex - 1);
      } else {
        this.goToPhilosophy();
      }
    }

    goToReview() {
      this.performAutoSave();
      this.currentScreen = 'review';
      this.render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ========================================================
    // MAIN SCREEN RENDERER
    // ========================================================
    render() {
      const root = document.getElementById('app-root');
      this.updateHeaderProgress();

      if (this.currentScreen === 'welcome') {
        root.innerHTML = this.renderWelcomeScreen();
      } else if (this.currentScreen === 'philosophy') {
        root.innerHTML = this.renderPhilosophyScreen();
      } else if (this.currentScreen.startsWith('chapter-')) {
        root.innerHTML = this.renderChapterScreen(this.currentChapterIndex);
      } else if (this.currentScreen === 'review') {
        root.innerHTML = this.renderReviewScreen();
      } else if (this.currentScreen === 'success') {
        root.innerHTML = this.renderSuccessScreen();
      }

      if (window.lucide) {
        window.lucide.createIcons();
      }
    }

    // ========================================================
    // SCREEN 1: BRAND WELCOME & ENTRANCE
    // ========================================================
    renderWelcomeScreen() {
      return `
        <div class="animate-fade-in max-w-4xl mx-auto text-center py-6 sm:py-16 space-y-8 sm:space-y-12">
          
          <!-- Official Geometric Brand Logo -->
          <div class="flex flex-col items-center justify-center space-y-4">
            <div class="w-24 h-24 sm:w-32 sm:h-32 p-2 bg-white rounded-lg shadow-luxury border border-brand-border/60">
              <img src="/static/brand/logo.svg" alt="Shameer Associates" class="w-full h-full object-contain" />
            </div>
            <div class="space-y-1">
              <h1 class="font-serif text-2xl sm:text-4xl font-bold tracking-[0.25em] text-brand-black">
                SHAMEER ASSOCIATES
              </h1>
              <p class="text-xs sm:text-sm font-semibold tracking-[0.35em] text-brand-bronze uppercase">
                ARCHITECTURE • INTERIORS • LANDSCAPE
              </p>
            </div>
          </div>

          <!-- Motto & Headline -->
          <div class="space-y-3 max-w-2xl mx-auto">
            <div class="w-16 h-0.5 bg-brand-bronze mx-auto"></div>
            <h2 class="font-serif text-3xl sm:text-5xl font-bold text-brand-black tracking-tight leading-tight">
              YOUR HOME.<br/>
              YOUR STORY.<br/>
              YOUR DESIGN.
            </h2>
            <p class="text-sm sm:text-base text-brand-slate font-light leading-relaxed pt-2">
              Before we design your home, we want to understand the people who will live in it — their routines, priorities, needs and vision.
            </p>
          </div>

          <!-- ICREATE Studio Values Grid -->
          <div class="bg-white p-6 sm:p-8 rounded-lg shadow-luxury border border-brand-border max-w-3xl mx-auto text-left">
            <div class="flex items-center justify-between pb-4 border-b border-brand-border mb-6">
              <span class="text-xs font-bold tracking-[0.2em] text-brand-bronze uppercase">Our Design Philosophy</span>
              <span class="font-serif font-bold text-sm tracking-widest text-brand-black">ICREATE</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-brand-slate">
              <div><b class="text-brand-black font-semibold">Integrity</b> — in our commitments & transparency</div>
              <div><b class="text-brand-black font-semibold">Creativity</b> — in every unique architectural solution</div>
              <div><b class="text-brand-black font-semibold">Relationships</b> — built through listening and respect</div>
              <div><b class="text-brand-black font-semibold">Excellence</b> — in structural quality & execution</div>
              <div><b class="text-brand-black font-semibold">Attention to Detail</b> — meticulous craftsmanship</div>
              <div><b class="text-brand-black font-semibold">Timeliness</b> — respecting time & client budgets</div>
              <div class="sm:col-span-2"><b class="text-brand-black font-semibold">Evolution</b> — continuous innovation & climate-responsive learning</div>
            </div>
            <p class="text-xs text-brand-muted italic mt-6 pt-4 border-t border-brand-border leading-relaxed">
              "We believe a home should be created with honesty, clarity and care—protecting our clients from costly mistakes while transforming their dreams into a timeless space that truly belongs to them."
            </p>
          </div>

          <!-- Primary CTA Button -->
          <div class="pt-4 space-y-3">
            <button onclick="window.app.goToPhilosophy()" class="px-8 sm:px-12 py-4 bg-brand-black hover:bg-brand-bronze text-white text-xs sm:text-sm font-bold tracking-[0.25em] uppercase rounded-sm shadow-xl hover:shadow-2xl transition-all duration-300 inline-flex items-center space-x-3 group">
              <span>BEGIN YOUR DESIGN JOURNEY</span>
              <i data-lucide="arrow-right" class="w-4 h-4 group-hover:translate-x-1 transition-transform"></i>
            </button>
            <p class="text-xs text-brand-muted">
              There are no right or wrong answers. Answer openly based on how you genuinely live.
            </p>
          </div>

        </div>
      `;
    }

    // ========================================================
    // SCREEN 2: BEFORE YOU BEGIN (5 THOUGHTS)
    // ========================================================
    renderPhilosophyScreen() {
      const data = this.schema.before_you_begin;
      return `
        <div class="animate-fade-in max-w-4xl mx-auto py-6 sm:py-10 space-y-8">
          
          <div class="text-center space-y-3">
            <span class="text-xs font-bold tracking-[0.25em] text-brand-bronze uppercase">Before You Begin</span>
            <h2 class="font-serif text-3xl sm:text-4xl font-bold text-brand-black">A Gentle Reminder</h2>
            <p class="text-xs sm:text-sm text-brand-muted max-w-2xl mx-auto leading-relaxed">
              ${data.subtitle}
            </p>
          </div>

          <!-- 5 Philosophy Cards -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 pt-4">
            ${data.thoughts.map((t, idx) => `
              <div class="bg-white p-6 rounded-lg shadow-luxury border border-brand-border hover:border-brand-bronze transition-all duration-200 space-y-3 ${idx === 4 ? 'md:col-span-2' : ''}">
                <div class="flex items-center space-x-3">
                  <span class="w-6 h-6 rounded-full bg-brand-lightGray text-brand-black flex items-center justify-center text-xs font-bold font-serif">
                    0${idx + 1}
                  </span>
                  <h3 class="font-serif text-base sm:text-lg font-bold text-brand-black">${t.title}</h3>
                </div>
                <p class="text-xs sm:text-sm text-brand-slate leading-relaxed font-light">
                  ${t.content}
                </p>
              </div>
            `).join('')}
          </div>

          <!-- Bottom CTA -->
          <div class="text-center pt-8 space-y-4">
            <button onclick="window.app.startQuestionnaire()" class="px-10 py-4 bg-brand-black hover:bg-brand-bronze text-white text-xs sm:text-sm font-bold tracking-[0.25em] uppercase rounded-sm shadow-xl hover:shadow-2xl transition-all duration-300 inline-flex items-center space-x-3 group">
              <span>LET'S BEGIN</span>
              <i data-lucide="arrow-right" class="w-4 h-4 group-hover:translate-x-1 transition-transform"></i>
            </button>
            <div>
              <button onclick="window.app.goToWelcome()" class="text-xs text-brand-muted hover:text-brand-black underline tracking-wider uppercase">
                Back to Introduction
              </button>
            </div>
          </div>

        </div>
      `;
    }

    // ========================================================
    // SCREEN 3: CHAPTER QUESTIONNAIRE ENGINE
    // ========================================================
    renderChapterScreen(chapterIndex) {
      const chapter = this.schema.chapters[chapterIndex];
      const isFirst = chapterIndex === 0;
      const isLast = chapterIndex === this.schema.chapters.length - 1;

      return `
        <div class="animate-fade-in max-w-4xl mx-auto space-y-8 sm:space-y-12">
          
          <!-- Chapter Banner -->
          <div class="border-b border-brand-border pb-6 space-y-2">
            <div class="flex items-center space-x-2">
              <span class="px-2.5 py-0.5 bg-brand-black text-white text-[10px] font-bold tracking-widest uppercase rounded-xs">
                CHAPTER ${chapter.number}
              </span>
              <span class="text-xs font-semibold tracking-wider text-brand-muted uppercase">
                Part ${chapterIndex + 1} of ${this.schema.chapters.length}
              </span>
            </div>
            <h2 class="font-serif text-2xl sm:text-4xl font-bold text-brand-black">
              ${chapter.title}
            </h2>
            <p class="text-xs sm:text-sm text-brand-muted leading-relaxed">
              ${chapter.description}
            </p>
          </div>

          <!-- Sections Container -->
          <div class="space-y-10">
            ${chapter.sections.map(sec => this.renderSection(sec)).join('')}
          </div>

          <!-- Bottom Step Navigation Bar -->
          <div class="pt-8 border-t border-brand-border flex flex-col sm:flex-row items-center justify-between gap-4">
            <button onclick="window.app.prevChapter()" class="w-full sm:w-auto px-6 py-3.5 border border-brand-border hover:border-brand-black text-brand-black text-xs font-bold tracking-widest uppercase rounded-sm bg-white transition-all flex items-center justify-center space-x-2">
              <i data-lucide="arrow-left" class="w-4 h-4"></i>
              <span>${isFirst ? 'Before You Begin' : 'Previous Chapter'}</span>
            </button>

            <div class="flex items-center space-x-3 w-full sm:w-auto">
              <button onclick="window.app.nextChapter()" class="w-full sm:w-auto px-10 py-3.5 bg-brand-black hover:bg-brand-bronze text-white text-xs font-bold tracking-widest uppercase rounded-sm shadow-lg transition-all flex items-center justify-center space-x-2 group">
                <span>${isLast ? 'Proceed to Review' : 'Save & Continue'}</span>
                <i data-lucide="arrow-right" class="w-4 h-4 group-hover:translate-x-1 transition-transform"></i>
              </button>
            </div>
          </div>

        </div>
      `;
    }

    // ========================================================
    // SECTION & QUESTION RENDERERS
    // ========================================================
    renderSection(sec) {
      if (sec.dependsOn) {
        const depVal = this.sessionData.answers[sec.dependsOn.id];
        if (sec.dependsOn.value && depVal !== sec.dependsOn.value) return '';
        if (sec.dependsOn.values && !sec.dependsOn.values.includes(depVal)) return '';
      }

      if (sec.type === 'dynamic-bedroom-container') {
        return this.renderDynamicBedroomsContainer();
      }

      return `
        <div class="bg-white p-6 sm:p-8 rounded-lg shadow-luxury border border-brand-border space-y-6">
          <div class="flex items-baseline justify-between border-b border-brand-border/60 pb-3">
            <h3 class="font-serif text-lg sm:text-xl font-bold text-brand-black flex items-center space-x-2">
              <span class="text-brand-bronze text-sm font-sans font-bold">${sec.number}</span>
              <span>${sec.title}</span>
            </h3>
          </div>

          <div class="grid grid-cols-1 gap-6">
            ${sec.questions ? sec.questions.map(q => this.renderQuestion(q)).join('') : ''}
          </div>
        </div>
      `;
    }

    renderQuestion(q) {
      // Check dependsOn condition
      if (q.dependsOn) {
        const depVal = this.sessionData.answers[q.dependsOn.id];
        if (q.dependsOn.value && depVal !== q.dependsOn.value) return '';
        if (q.dependsOn.values && !q.dependsOn.values.includes(depVal)) return '';
      }

      const val = this.sessionData.answers[q.id];

      // Tooltip Button Component
      const tooltipBtn = q.hasTooltip ? `
        <button type="button" onclick="window.app.openTooltip('${q.hasTooltip}')" class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-lightGray hover:bg-brand-black hover:text-white text-brand-bronze transition-colors text-[10px] ml-1.5 focus:outline-none" title="Architectural Explanation">
          ⓘ
        </button>
      ` : '';

      switch (q.type) {
        case 'text':
        case 'email':
        case 'tel':
          return `
            <div class="space-y-1.5">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">
                ${q.label} ${q.required ? '<span class="text-red-500">*</span>' : ''} ${tooltipBtn}
              </label>
              <input type="${q.type}" value="${val || ''}" placeholder="${q.placeholder || ''}" oninput="window.app.handleInput('${q.id}', this.value)" class="w-full px-4 py-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black placeholder:text-brand-muted/60 focus:bg-white" />
            </div>
          `;

        case 'number':
          return `
            <div class="space-y-1.5">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">
                ${q.label} ${q.required ? '<span class="text-red-500">*</span>' : ''} ${tooltipBtn}
              </label>
              <input type="number" value="${val || ''}" placeholder="${q.placeholder || ''}" oninput="window.app.handleInput('${q.id}', this.value)" class="w-full sm:w-48 px-4 py-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black placeholder:text-brand-muted/60 focus:bg-white" />
            </div>
          `;

        case 'textarea':
          return `
            <div class="space-y-1.5">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">
                ${q.label} ${q.required ? '<span class="text-red-500">*</span>' : ''} ${tooltipBtn}
              </label>
              <textarea rows="3" placeholder="${q.placeholder || ''}" oninput="window.app.handleInput('${q.id}', this.value)" class="w-full px-4 py-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black placeholder:text-brand-muted/60 focus:bg-white leading-relaxed">${val || ''}</textarea>
            </div>
          `;

        case 'single-select':
          return `
            <div class="space-y-2">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">
                ${q.label} ${q.required ? '<span class="text-red-500">*</span>' : ''} ${tooltipBtn}
              </label>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                ${q.options.map(opt => {
                  const isSelected = val === opt;
                  return `
                    <div onclick="window.app.handleSingleSelect('${q.id}', '${this.escapeHtml(opt)}')" class="option-card cursor-pointer p-3 rounded border text-xs flex items-center justify-between ${isSelected ? 'selected border-brand-black bg-white font-semibold' : 'border-brand-border bg-brand-offwhite/50 hover:bg-white hover:border-brand-slate text-brand-slate'}">
                      <span>${opt}</span>
                      <div class="w-4 h-4 rounded-full border flex items-center justify-center ml-2 flex-shrink-0 ${isSelected ? 'border-brand-black bg-brand-black text-white' : 'border-brand-border bg-white'}">
                        ${isSelected ? '<i data-lucide="check" class="w-2.5 h-2.5"></i>' : ''}
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          `;

        case 'multi-select':
          const currentList = Array.isArray(val) ? val : [];
          return `
            <div class="space-y-2">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">
                ${q.label} ${tooltipBtn}
              </label>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                ${q.options.map(opt => {
                  const isSelected = currentList.includes(opt);
                  return `
                    <div onclick="window.app.handleMultiSelect('${q.id}', '${this.escapeHtml(opt)}')" class="option-card cursor-pointer p-3 rounded border text-xs flex items-center justify-between ${isSelected ? 'selected border-brand-black bg-white font-semibold' : 'border-brand-border bg-brand-offwhite/50 hover:bg-white hover:border-brand-slate text-brand-slate'}">
                      <span>${opt}</span>
                      <div class="w-4 h-4 rounded border flex items-center justify-center ml-2 flex-shrink-0 ${isSelected ? 'border-brand-black bg-brand-black text-white' : 'border-brand-border bg-white'}">
                        ${isSelected ? '<i data-lucide="check" class="w-2.5 h-2.5"></i>' : ''}
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          `;

        case 'family-builder':
          return this.renderFamilyBuilder();

        case 'visual-gallery':
          return this.renderVisualGallery(q.category, q.label, q.helpText);

        case 'file-upload':
          return this.renderFileUpload(q);

        default:
          return '';
      }
    }

    // ========================================================
    // FAMILY BUILDER COMPONENT
    // ========================================================
    renderFamilyBuilder() {
      const members = this.sessionData.family_members || [];
      return `
        <div class="space-y-4 pt-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold tracking-wider text-brand-black uppercase">Family & Household Members</span>
            <button type="button" onclick="window.app.addFamilyMember()" class="px-3 py-1.5 bg-brand-black hover:bg-brand-bronze text-white text-[11px] font-semibold tracking-wider uppercase rounded-sm transition-colors flex items-center space-x-1.5">
              <i data-lucide="plus" class="w-3.5 h-3.5"></i>
              <span>Add Member</span>
            </button>
          </div>

          ${members.length === 0 ? `
            <div class="p-4 border border-dashed border-brand-border rounded text-center text-xs text-brand-muted bg-brand-offwhite/50">
              No family members added yet. Click "+ Add Member" above to add family details (Children, Teenagers, Adults, Seniors).
            </div>
          ` : `
            <div class="space-y-3">
              ${members.map((m, idx) => `
                <div class="p-4 bg-brand-offwhite border border-brand-border rounded-lg space-y-3 relative">
                  <div class="flex items-center justify-between border-b border-brand-border/60 pb-2">
                    <span class="text-xs font-bold font-serif text-brand-black">Member #${idx + 1}</span>
                    <button type="button" onclick="window.app.removeFamilyMember(${idx})" class="text-brand-muted hover:text-red-600 transition-colors p-1" title="Remove Member">
                      <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                  </div>
                  <div class="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
                    <div>
                      <label class="block text-[10px] font-bold text-brand-muted uppercase mb-1">User Group</label>
                      <select onchange="window.app.updateFamilyMember(${idx}, 'user_group', this.value)" class="w-full p-2 bg-white border border-brand-border rounded text-xs">
                        <option value="Adults" ${m.user_group === 'Adults' ? 'selected' : ''}>Adults</option>
                        <option value="Children" ${m.user_group === 'Children' ? 'selected' : ''}>Children</option>
                        <option value="Teenagers" ${m.user_group === 'Teenagers' ? 'selected' : ''}>Teenagers</option>
                        <option value="Elderly / Senior" ${m.user_group === 'Elderly / Senior' ? 'selected' : ''}>Elderly / Senior</option>
                        <option value="Other" ${m.user_group === 'Other' ? 'selected' : ''}>Other</option>
                      </select>
                    </div>
                    <div>
                      <label class="block text-[10px] font-bold text-brand-muted uppercase mb-1">Count</label>
                      <input type="number" min="1" value="${m.count || 1}" oninput="window.app.updateFamilyMember(${idx}, 'count', this.value)" class="w-full p-2 bg-white border border-brand-border rounded text-xs" />
                    </div>
                    <div>
                      <label class="block text-[10px] font-bold text-brand-muted uppercase mb-1">Gender</label>
                      <input type="text" placeholder="e.g. Male, Female" value="${m.gender || ''}" oninput="window.app.updateFamilyMember(${idx}, 'gender', this.value)" class="w-full p-2 bg-white border border-brand-border rounded text-xs" />
                    </div>
                    <div>
                      <label class="block text-[10px] font-bold text-brand-muted uppercase mb-1">Age Range</label>
                      <input type="text" placeholder="e.g. 6–10, 35–40" value="${m.age_range || ''}" oninput="window.app.updateFamilyMember(${idx}, 'age_range', this.value)" class="w-full p-2 bg-white border border-brand-border rounded text-xs" />
                    </div>
                    <div class="sm:col-span-4">
                      <label class="block text-[10px] font-bold text-brand-muted uppercase mb-1">Special Note / Routine Needs</label>
                      <input type="text" placeholder="e.g. Needs quiet study desk, ground floor room, wheelchair friendly..." value="${m.special_note || ''}" oninput="window.app.updateFamilyMember(${idx}, 'special_note', this.value)" class="w-full p-2 bg-white border border-brand-border rounded text-xs" />
                    </div>
                  </div>
                </div>
              `).join('')}
            </div>
          `}
        </div>
      `;
    }

    addFamilyMember() {
      if (!this.sessionData.family_members) this.sessionData.family_members = [];
      this.sessionData.family_members.push({
        user_group: 'Adults',
        count: 1,
        gender: '',
        age_range: '',
        special_note: ''
      });
      this.saveFamilyMembers();
      this.render();
    }

    removeFamilyMember(idx) {
      if (this.sessionData.family_members) {
        this.sessionData.family_members.splice(idx, 1);
        this.saveFamilyMembers();
        this.render();
      }
    }

    updateFamilyMember(idx, field, value) {
      if (this.sessionData.family_members && this.sessionData.family_members[idx]) {
        this.sessionData.family_members[idx][field] = value;
        this.saveFamilyMembers();
      }
    }

    async saveFamilyMembers() {
      if (!this.sessionToken) return;
      try {
        await fetch(`/api/session/${this.sessionToken}/save_family`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ family_members: this.sessionData.family_members })
        });
        this.updateSaveStatus('All changes saved');
      } catch (err) {
        console.error('Error saving family members:', err);
      }
    }

    // ========================================================
    // DYNAMIC BEDROOMS BUILDER
    // ========================================================
    renderDynamicBedroomsContainer() {
      const countStr = this.sessionData.answers['additional_bedrooms_count'] || '0';
      const count = countStr === '5+' ? 5 : parseInt(countStr, 10) || 0;

      if (count === 0) {
        return '';
      }

      // Ensure dynamic rooms array matches count
      if (!this.sessionData.dynamic_rooms) this.sessionData.dynamic_rooms = [];
      while (this.sessionData.dynamic_rooms.length < count) {
        const idx = this.sessionData.dynamic_rooms.length + 1;
        this.sessionData.dynamic_rooms.push({
          room_id: `room_${idx}`,
          room_name: `Additional Bedroom ${idx}`,
          room_type: 'additional_bedroom',
          answers: {}
        });
      }
      if (this.sessionData.dynamic_rooms.length > count) {
        this.sessionData.dynamic_rooms = this.sessionData.dynamic_rooms.slice(0, count);
      }

      const templateQuestions = this.schema.dynamic_bedroom_template.questions;

      return `
        <div class="space-y-6">
          ${this.sessionData.dynamic_rooms.map((room, rIdx) => `
            <div class="bg-white p-6 sm:p-8 rounded-lg shadow-luxury border border-brand-border space-y-6">
              <div class="flex items-center justify-between border-b border-brand-border/60 pb-3">
                <h3 class="font-serif text-lg sm:text-xl font-bold text-brand-black flex items-center space-x-2">
                  <span class="text-brand-bronze text-sm font-sans font-bold">3.13.${rIdx + 3}</span>
                  <span>${room.room_name}</span>
                </h3>
              </div>

              <div class="grid grid-cols-1 gap-6">
                ${templateQuestions.map(q => this.renderDynamicRoomQuestion(rIdx, q)).join('')}
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }

    renderDynamicRoomQuestion(roomIdx, q) {
      const room = this.sessionData.dynamic_rooms[roomIdx];
      const val = room.answers ? room.answers[q.id] : undefined;

      switch (q.type) {
        case 'single-select':
          return `
            <div class="space-y-2">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">${q.label}</label>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                ${q.options.map(opt => {
                  const isSelected = val === opt;
                  return `
                    <div onclick="window.app.handleDynamicRoomSingleSelect(${roomIdx}, '${q.id}', '${this.escapeHtml(opt)}')" class="option-card cursor-pointer p-3 rounded border text-xs flex items-center justify-between ${isSelected ? 'selected border-brand-black bg-white font-semibold' : 'border-brand-border bg-brand-offwhite/50 hover:bg-white hover:border-brand-slate text-brand-slate'}">
                      <span>${opt}</span>
                      <div class="w-4 h-4 rounded-full border flex items-center justify-center ml-2 flex-shrink-0 ${isSelected ? 'border-brand-black bg-brand-black text-white' : 'border-brand-border bg-white'}">
                        ${isSelected ? '<i data-lucide="check" class="w-2.5 h-2.5"></i>' : ''}
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          `;

        case 'multi-select':
          const currentList = Array.isArray(val) ? val : [];
          return `
            <div class="space-y-2">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">${q.label}</label>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                ${q.options.map(opt => {
                  const isSelected = currentList.includes(opt);
                  return `
                    <div onclick="window.app.handleDynamicRoomMultiSelect(${roomIdx}, '${q.id}', '${this.escapeHtml(opt)}')" class="option-card cursor-pointer p-3 rounded border text-xs flex items-center justify-between ${isSelected ? 'selected border-brand-black bg-white font-semibold' : 'border-brand-border bg-brand-offwhite/50 hover:bg-white hover:border-brand-slate text-brand-slate'}">
                      <span>${opt}</span>
                      <div class="w-4 h-4 rounded border flex items-center justify-center ml-2 flex-shrink-0 ${isSelected ? 'border-brand-black bg-brand-black text-white' : 'border-brand-border bg-white'}">
                        ${isSelected ? '<i data-lucide="check" class="w-2.5 h-2.5"></i>' : ''}
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          `;

        case 'textarea':
          return `
            <div class="space-y-1.5">
              <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">${q.label}</label>
              <textarea rows="2" placeholder="${q.placeholder || ''}" oninput="window.app.handleDynamicRoomInput(${roomIdx}, '${q.id}', this.value)" class="w-full px-4 py-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black placeholder:text-brand-muted/60 focus:bg-white leading-relaxed">${val || ''}</textarea>
            </div>
          `;

        default:
          return '';
      }
    }

    handleDynamicRoomSingleSelect(roomIdx, field, value) {
      if (this.sessionData.dynamic_rooms[roomIdx]) {
        if (!this.sessionData.dynamic_rooms[roomIdx].answers) this.sessionData.dynamic_rooms[roomIdx].answers = {};
        this.sessionData.dynamic_rooms[roomIdx].answers[field] = value;
        this.saveDynamicRooms();
        this.render();
      }
    }

    handleDynamicRoomMultiSelect(roomIdx, field, value) {
      if (this.sessionData.dynamic_rooms[roomIdx]) {
        if (!this.sessionData.dynamic_rooms[roomIdx].answers) this.sessionData.dynamic_rooms[roomIdx].answers = {};
        let list = this.sessionData.dynamic_rooms[roomIdx].answers[field];
        if (!Array.isArray(list)) list = [];
        if (list.includes(value)) {
          list = list.filter(item => item !== value);
        } else {
          list.push(value);
        }
        this.sessionData.dynamic_rooms[roomIdx].answers[field] = list;
        this.saveDynamicRooms();
        this.render();
      }
    }

    handleDynamicRoomInput(roomIdx, field, value) {
      if (this.sessionData.dynamic_rooms[roomIdx]) {
        if (!this.sessionData.dynamic_rooms[roomIdx].answers) this.sessionData.dynamic_rooms[roomIdx].answers = {};
        this.sessionData.dynamic_rooms[roomIdx].answers[field] = value;
        this.saveDynamicRooms();
      }
    }

    async saveDynamicRooms() {
      if (!this.sessionToken) return;
      try {
        await fetch(`/api/session/${this.sessionToken}/save_rooms`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dynamic_rooms: this.sessionData.dynamic_rooms })
        });
        this.updateSaveStatus('All changes saved');
      } catch (err) {
        console.error('Error saving dynamic rooms:', err);
      }
    }

    // ========================================================
    // VISUAL REFERENCE GALLERY ENGINE
    // ========================================================
    renderVisualGallery(category, label, helpText) {
      const items = this.visuals ? this.visuals[category] || [] : [];
      const selectedStyle = this.sessionData.selected_visuals[category];

      return `
        <div class="space-y-4 pt-2">
          <div class="space-y-1">
            <span class="text-xs font-bold tracking-wider text-brand-black uppercase">${label}</span>
            ${helpText ? `<p class="text-xs text-brand-muted leading-relaxed">${helpText}</p>` : ''}
          </div>

          <!-- Gallery Grid -->
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            ${items.map(item => {
              const isSelected = selectedStyle && (selectedStyle.style_id === item.id || selectedStyle.style_number === item.styleNumber);
              
              // Handle Single vs Paired Images
              let imgHtml = '';
              if (category === 'formal_living_dining') {
                imgHtml = `
                  <div class="grid grid-cols-2 gap-1 bg-brand-lightGray">
                    <div class="visual-card-img-container aspect-square relative cursor-pointer overflow-hidden flex items-center justify-center bg-brand-lightGray" onclick="window.app.openLightbox('${category}', '${item.id}', '${item.livingImage}', 'Formal Living')">
                      <img src="${item.livingImage}" alt="${item.styleName} Living" loading="lazy" class="visual-card-img w-full h-full object-contain object-center animate-fade-in" />
                      <span class="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 text-[9px] font-bold text-white uppercase rounded-xs">Living</span>
                    </div>
                    <div class="visual-card-img-container aspect-square relative cursor-pointer overflow-hidden flex items-center justify-center bg-brand-lightGray" onclick="window.app.openLightbox('${category}', '${item.id}', '${item.diningImage}', 'Dining')">
                      <img src="${item.diningImage}" alt="${item.styleName} Dining" loading="lazy" class="visual-card-img w-full h-full object-contain object-center animate-fade-in" />
                      <span class="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 text-[9px] font-bold text-white uppercase rounded-xs">Dining</span>
                    </div>
                  </div>
                `;
              } else if (category === 'bedroom') {
                imgHtml = `
                  <div class="grid grid-cols-2 gap-1 bg-brand-lightGray">
                    <div class="visual-card-img-container aspect-square relative cursor-pointer overflow-hidden flex items-center justify-center bg-brand-lightGray" onclick="window.app.openLightbox('${category}', '${item.id}', '${item.bedroomImage}', 'Bedroom')">
                      <img src="${item.bedroomImage}" alt="${item.styleName} Bedroom" loading="lazy" class="visual-card-img w-full h-full object-contain object-center animate-fade-in" />
                      <span class="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 text-[9px] font-bold text-white uppercase rounded-xs">Bed</span>
                    </div>
                    <div class="visual-card-img-container aspect-square relative cursor-pointer overflow-hidden flex items-center justify-center bg-brand-lightGray" onclick="window.app.openLightbox('${category}', '${item.id}', '${item.wardrobeImage}', 'Wardrobe / Dressing')">
                      <img src="${item.wardrobeImage}" alt="${item.styleName} Wardrobe" loading="lazy" class="visual-card-img w-full h-full object-contain object-center animate-fade-in" />
                      <span class="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 text-[9px] font-bold text-white uppercase rounded-xs">Dressing</span>
                    </div>
                  </div>
                `;
              } else {
                imgHtml = `
                  <div class="visual-card-img-container aspect-square relative cursor-pointer bg-brand-lightGray overflow-hidden flex items-center justify-center" onclick="window.app.openLightbox('${category}', '${item.id}', '${item.image}')">
                    <img src="${item.image}" alt="${item.styleName}" loading="lazy" class="visual-card-img w-full h-full object-contain object-center animate-fade-in" />
                    <div class="absolute inset-0 bg-black/0 hover:bg-black/20 transition-colors flex items-center justify-center opacity-0 hover:opacity-100">
                      <span class="px-2.5 py-1 bg-black/75 text-white text-[10px] font-semibold tracking-widest uppercase rounded shadow backdrop-blur-xs">
                        View Fullscreen
                      </span>
                    </div>
                  </div>
                `;
              }

              return `
                <div class="visual-card rounded-lg overflow-hidden bg-white border ${isSelected ? 'selected border-brand-black' : 'border-brand-border'} shadow-luxury flex flex-col justify-between">
                  <div>
                    ${imgHtml}
                    <div class="p-4 space-y-2">
                      <div class="flex items-baseline justify-between">
                        <span class="text-[10px] font-bold text-brand-bronze uppercase tracking-widest">Style ${item.styleNumber}</span>
                        ${isSelected ? '<span class="px-2 py-0.5 bg-brand-black text-white text-[9px] font-bold uppercase tracking-wider rounded-xs flex items-center space-x-1"><i data-lucide="check" class="w-3 h-3"></i><span>Selected</span></span>' : ''}
                      </div>
                      <h4 class="font-serif text-base font-bold text-brand-black">${item.styleName}</h4>
                      <p class="text-[11px] text-brand-muted leading-relaxed line-clamp-2">
                        ${item.description || item.designBrief || ''}
                      </p>
                    </div>
                  </div>

                  <div class="p-4 pt-0">
                    <button type="button" onclick="window.app.selectVisual('${category}', '${item.id}')" class="w-full py-2.5 px-3 text-xs font-bold tracking-wider uppercase rounded transition-colors flex items-center justify-center space-x-2 ${isSelected ? 'bg-brand-black text-white' : 'bg-brand-lightGray hover:bg-brand-black hover:text-white text-brand-black'}">
                      <i data-lucide="check" class="w-3.5 h-3.5"></i>
                      <span>${isSelected ? 'Selected Reference' : 'Select Style'}</span>
                    </button>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    async selectVisual(category, styleId) {
      const items = this.visuals ? this.visuals[category] || [] : [];
      const item = items.find(i => i.id === styleId);
      if (!item) return;

      this.sessionData.selected_visuals[category] = {
        style_id: item.id,
        style_name: item.styleName,
        style_number: item.styleNumber,
        image_url: item.image || '',
        living_image_url: item.livingImage || '',
        dining_image_url: item.diningImage || '',
        bedroom_image_url: item.bedroomImage || '',
        wardrobe_image_url: item.wardrobeImage || ''
      };

      try {
        await fetch(`/api/session/${this.sessionToken}/save_visual`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category, style: item })
        });
        this.updateSaveStatus('All changes saved');
        this.render();
      } catch (err) {
        console.error('Error saving visual selection:', err);
      }
    }

    // ========================================================
    // LIGHTBOX COMPONENT
    // ========================================================
    openLightbox(category, styleId, specificImgUrl, subLabel = '') {
      const items = this.visuals ? this.visuals[category] || [] : [];
      const item = items.find(i => i.id === styleId);
      if (!item) return;

      this.activeLightboxData = { category, item };

      const modal = document.getElementById('lightbox-modal');
      const img = document.getElementById('lightbox-image');
      const cat = document.getElementById('lightbox-category');
      const title = document.getElementById('lightbox-title');
      const desc = document.getElementById('lightbox-description');
      const feels = document.getElementById('lightbox-feels');
      const feelsSection = document.getElementById('lightbox-feels-section');
      const selectBtn = document.getElementById('lightbox-select-btn');
      const selectText = document.getElementById('lightbox-select-text');

      img.src = specificImgUrl || item.image || item.livingImage || item.bedroomImage;
      cat.textContent = subLabel ? `${category.replace(/_/g, ' ')} — ${subLabel}` : category.replace(/_/g, ' ');
      title.textContent = `Style ${item.styleNumber}: ${item.styleName}`;
      desc.textContent = item.description || item.designBrief || 'Architectural style reference.';

      if (item.howItFeels) {
        feelsSection.classList.remove('hidden');
        feels.textContent = `"${item.howItFeels}"`;
      } else {
        feelsSection.classList.add('hidden');
      }

      const isSelected = this.sessionData.selected_visuals[category] && this.sessionData.selected_visuals[category].style_id === item.id;
      if (isSelected) {
        selectBtn.classList.add('bg-emerald-600', 'text-white');
        selectBtn.classList.remove('bg-white', 'text-brand-black');
        selectText.textContent = '✓ Selected Reference';
      } else {
        selectBtn.classList.remove('bg-emerald-600', 'text-white');
        selectBtn.classList.add('bg-white', 'text-brand-black');
        selectText.textContent = 'Select This Style';
      }

      const imgContainer = document.getElementById('lightbox-img-container') || img.parentElement;
      if (imgContainer) {
        imgContainer.onclick = () => this.openGlobalLightbox(img.src);
      }

      this.lockBodyScroll();
      modal.classList.remove('hidden');
      setTimeout(() => {
        modal.classList.remove('opacity-0');
      }, 10);

      if (window.lucide) window.lucide.createIcons();
    }

    closeLightbox() {
      const modal = document.getElementById('lightbox-modal');
      if (modal && !modal.classList.contains('hidden')) {
        modal.classList.add('opacity-0');
        setTimeout(() => {
          modal.classList.add('hidden');
          this.activeLightboxData = null;
          this.unlockBodyScroll();
        }, 200);
      }
    }

    handleLightboxBackdrop(e) {
      if (e.target.id === 'lightbox-modal') {
        this.closeLightbox();
      }
    }

    // ========================================================
    // REUSABLE GLOBAL IMAGE LIGHTBOX (Fullscreen Enlargement)
    // ========================================================
    openGlobalLightbox(src) {
      if (!src) return;
      const modal = document.getElementById('global-image-lightbox');
      const img = document.getElementById('global-lightbox-image');
      if (!modal || !img) return;

      img.src = src;
      this.lockBodyScroll();
      modal.classList.remove('hidden');
      setTimeout(() => {
        modal.classList.remove('opacity-0');
      }, 10);

      if (window.lucide) window.lucide.createIcons();
    }

    closeGlobalLightbox() {
      const modal = document.getElementById('global-image-lightbox');
      if (modal && !modal.classList.contains('hidden')) {
        modal.classList.add('opacity-0');
        setTimeout(() => {
          modal.classList.add('hidden');
          this.unlockBodyScroll();
        }, 200);
      }
    }

    handleGlobalLightboxBackdrop(e) {
      if (e.target.id === 'global-image-lightbox' || (e.target.closest('#global-image-lightbox') && !e.target.closest('#global-lightbox-image'))) {
        this.closeGlobalLightbox();
      }
    }

    toggleSelectFromLightbox() {
      if (this.activeLightboxData) {
        const { category, item } = this.activeLightboxData;
        this.selectVisual(category, item.id);
        this.closeLightbox();
      }
    }

    // ========================================================
    // TECHNICAL TOOLTIPS (ⓘ)
    // ========================================================
    openTooltip(key) {
      const modal = document.getElementById('tooltip-modal');
      const title = document.getElementById('tooltip-title');
      const content = document.getElementById('tooltip-content');

      const glossary = this.schema.technical_glossary || {};
      const titles = {
        natural_light: 'Natural Light',
        skylight: 'Skylights',
        natural_ventilation: 'Natural Ventilation',
        cross_ventilation: 'Cross Ventilation',
        passive_cooling: 'Passive Cooling',
        cavity_wall: 'Double / Cavity Wall',
        louvers_sunshades: 'Louvres / Sunshades',
        zoning: 'Space Zoning',
        mep: 'MEP Engineering Design',
        layered_lighting: 'Layered Lighting Design',
        home_automation: 'Home Automation',
        tensile_structure: 'Tensile Fabric Structure'
      };

      title.textContent = titles[key] || key.replace(/_/g, ' ');
      content.textContent = glossary[key] || 'Technical architectural explanation.';

      modal.classList.remove('hidden');
      setTimeout(() => {
        modal.classList.remove('opacity-0');
      }, 10);
    }

    closeTooltip() {
      const modal = document.getElementById('tooltip-modal');
      if (modal && !modal.classList.contains('hidden')) {
        modal.classList.add('opacity-0');
        setTimeout(() => {
          modal.classList.add('hidden');
        }, 200);
      }
    }

    handleTooltipBackdrop(e) {
      if (e.target.id === 'tooltip-modal') {
        this.closeTooltip();
      }
    }

    // ========================================================
    // SAVE & RESUME MODAL
    // ========================================================
    openSaveModal() {
      const modal = document.getElementById('save-modal');
      const resumeInput = document.getElementById('resume-link-input');
      const msg = document.getElementById('copy-success-msg');
      if (msg) msg.classList.add('hidden');
      if (resumeInput) resumeInput.value = window.location.href;

      modal.classList.remove('hidden');
      setTimeout(() => {
        modal.classList.remove('opacity-0');
      }, 10);
    }

    closeSaveModal() {
      const modal = document.getElementById('save-modal');
      if (modal && !modal.classList.contains('hidden')) {
        modal.classList.add('opacity-0');
        setTimeout(() => {
          modal.classList.add('hidden');
        }, 200);
      }
    }

    handleSaveModalBackdrop(e) {
      if (e.target.id === 'save-modal') {
        this.closeSaveModal();
      }
    }

    copyResumeLink() {
      const resumeInput = document.getElementById('resume-link-input');
      if (resumeInput) {
        resumeInput.select();
        navigator.clipboard.writeText(resumeInput.value);
        const msg = document.getElementById('copy-success-msg');
        if (msg) msg.classList.remove('hidden');
      }
    }

    // ========================================================
    // FILE UPLOAD COMPONENT
    // ========================================================
    renderFileUpload(q) {
      const uploads = this.sessionData.uploads || [];
      return `
        <div class="space-y-3 pt-2">
          <label class="block text-xs font-bold tracking-wider text-brand-black uppercase">${q.label}</label>
          ${q.helpText ? `<p class="text-xs text-brand-muted">${q.helpText}</p>` : ''}
          
          <div class="border-2 border-dashed border-brand-border hover:border-brand-black rounded-lg p-6 text-center bg-brand-offwhite/50 transition-colors">
            <input type="file" id="file-uploader-input" onchange="window.app.handleFileUpload(this.files)" class="hidden" multiple accept=".pdf,.png,.jpg,.jpeg,.dwg" />
            <label for="file-uploader-input" class="cursor-pointer flex flex-col items-center space-y-2">
              <div class="w-10 h-10 rounded-full bg-brand-lightGray flex items-center justify-center text-brand-black">
                <i data-lucide="upload-cloud" class="w-5 h-5"></i>
              </div>
              <span class="text-xs font-semibold text-brand-black">Click to select files or drag & drop</span>
              <span class="text-[11px] text-brand-muted">PDF, JPEG, PNG (Up to 32MB each)</span>
            </label>
          </div>

          ${uploads.length > 0 ? `
            <div class="space-y-2 pt-2">
              <span class="text-[11px] font-bold text-brand-muted uppercase">Uploaded Documents:</span>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                ${uploads.map(up => `
                  <div class="flex items-center justify-between p-2.5 bg-brand-offwhite border border-brand-border rounded text-xs">
                    <div class="flex items-center space-x-2 truncate">
                      <i data-lucide="file-text" class="w-4 h-4 text-brand-bronze flex-shrink-0"></i>
                      <span class="truncate font-medium">${up.original_filename}</span>
                    </div>
                    <span class="text-[10px] text-brand-muted flex-shrink-0 ml-2">${(up.file_size / 1024).toFixed(0)} KB</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      `;
    }

    async handleFileUpload(files) {
      if (!files || files.length === 0 || !this.sessionToken) return;
      this.updateSaveStatus('Uploading document...');

      for (let i = 0; i < files.length; i++) {
        const formData = new FormData();
        formData.append('file', files[i]);
        formData.append('category', 'site_document');

        try {
          const res = await fetch(`/api/session/${this.sessionToken}/upload`, {
            method: 'POST',
            body: formData
          });
          const data = await res.json();
          if (data.success) {
            if (!this.sessionData.uploads) this.sessionData.uploads = [];
            this.sessionData.uploads.unshift({
              file_id: data.file_id,
              original_filename: data.filename,
              file_size: data.size
            });
          }
        } catch (err) {
          console.error('File upload failed:', err);
        }
      }

      this.updateSaveStatus('All changes saved');
      this.render();
    }

    // ========================================================
    // INPUT HANDLERS
    // ========================================================
    handleInput(fieldId, value) {
      this.sessionData.answers[fieldId] = value;
      this.scheduleAutoSave();
    }

    handleSingleSelect(fieldId, value) {
      this.sessionData.answers[fieldId] = value;
      this.scheduleAutoSave();
      this.render();
    }

    handleMultiSelect(fieldId, value) {
      let currentList = this.sessionData.answers[fieldId];
      if (!Array.isArray(currentList)) currentList = [];
      if (currentList.includes(value)) {
        currentList = currentList.filter(item => item !== value);
      } else {
        currentList.push(value);
      }
      this.sessionData.answers[fieldId] = currentList;
      this.scheduleAutoSave();
      this.render();
    }

    // ========================================================
    // SCREEN 4: REVIEW & INSPIRATION SUMMARY
    // ========================================================
    renderReviewScreen() {
      const selectedExt = this.sessionData.selected_visuals.exterior;
      const selectedFLD = this.sessionData.selected_visuals.formal_living_dining;
      const selectedBed = this.sessionData.selected_visuals.bedroom;
      const selectedKit = this.sessionData.selected_visuals.kitchen;

      // Count unanswered optional questions
      let unansweredCount = 0;
      this.schema.chapters.forEach(ch => {
        ch.sections.forEach(sec => {
          if (sec.questions) {
            sec.questions.forEach(q => {
              if (q.type !== 'file-upload') {
                const val = this.sessionData.answers[q.id];
                if (val === undefined || val === null || val === "" || (Array.isArray(val) && val.length === 0)) {
                  unansweredCount++;
                }
              }
            });
          }
        });
      });

      return `
        <div class="animate-fade-in max-w-4xl mx-auto space-y-8 sm:space-y-12">
          
          <div class="border-b border-brand-border pb-6 space-y-2 text-center">
            <span class="text-xs font-bold tracking-[0.25em] text-brand-bronze uppercase">Design Brief Final Audit</span>
            <h2 class="font-serif text-3xl sm:text-4xl font-bold text-brand-black">Review Your Home Brief</h2>
            <p class="text-xs sm:text-sm text-brand-muted max-w-2xl mx-auto leading-relaxed">
              Review your answers and selected design styles below before submitting your brief to Shameer Associates.
            </p>
          </div>

          ${unansweredCount > 0 ? `
            <div class="p-4 bg-brand-lightGray border border-brand-border rounded-lg flex items-center justify-between">
              <div class="flex items-center space-x-3 text-xs text-brand-slate">
                <i data-lucide="info" class="w-4 h-4 text-brand-bronze flex-shrink-0"></i>
                <span>You have <b>${unansweredCount} optional questions</b> left unanswered. You may review them or proceed with submission.</span>
              </div>
            </div>
          ` : ''}

          <!-- Selected References Visual Summary Board -->
          <div class="bg-white p-6 sm:p-8 rounded-lg shadow-luxury border border-brand-border space-y-6">
            <div class="flex items-center justify-between border-b border-brand-border/60 pb-3">
              <h3 class="font-serif text-lg sm:text-xl font-bold text-brand-black">Selected Design References</h3>
              <span class="text-xs text-brand-bronze font-semibold uppercase tracking-wider">Your Visual Palette</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              
              <!-- Exterior -->
              <div class="bg-brand-offwhite p-3 rounded border border-brand-border space-y-2">
                <span class="text-[10px] font-bold tracking-wider text-brand-muted uppercase">01 Exterior</span>
                ${selectedExt ? `
                  <div class="aspect-[16/10] bg-black rounded overflow-hidden">
                    <img src="${selectedExt.image_url}" alt="${selectedExt.style_name}" class="w-full h-full object-cover" />
                  </div>
                  <p class="text-xs font-serif font-bold text-brand-black truncate">${selectedExt.style_name}</p>
                ` : `
                  <div class="aspect-[16/10] bg-brand-lightGray rounded flex items-center justify-center text-[11px] text-brand-muted">Not Selected</div>
                `}
                <button onclick="window.app.goToChapter(1)" class="text-[11px] text-brand-bronze font-semibold underline">Edit</button>
              </div>

              <!-- Living & Dining -->
              <div class="bg-brand-offwhite p-3 rounded border border-brand-border space-y-2">
                <span class="text-[10px] font-bold tracking-wider text-brand-muted uppercase">02 Living & Dining</span>
                ${selectedFLD ? `
                  <div class="aspect-[16/10] bg-black rounded overflow-hidden">
                    <img src="${selectedFLD.living_image_url}" alt="${selectedFLD.style_name}" class="w-full h-full object-cover" />
                  </div>
                  <p class="text-xs font-serif font-bold text-brand-black truncate">${selectedFLD.style_name}</p>
                ` : `
                  <div class="aspect-[16/10] bg-brand-lightGray rounded flex items-center justify-center text-[11px] text-brand-muted">Not Selected</div>
                `}
                <button onclick="window.app.goToChapter(2)" class="text-[11px] text-brand-bronze font-semibold underline">Edit</button>
              </div>

              <!-- Bedroom -->
              <div class="bg-brand-offwhite p-3 rounded border border-brand-border space-y-2">
                <span class="text-[10px] font-bold tracking-wider text-brand-muted uppercase">03 Bedroom & Wardrobe</span>
                ${selectedBed ? `
                  <div class="aspect-[16/10] bg-black rounded overflow-hidden">
                    <img src="${selectedBed.bedroom_image_url}" alt="${selectedBed.style_name}" class="w-full h-full object-cover" />
                  </div>
                  <p class="text-xs font-serif font-bold text-brand-black truncate">${selectedBed.style_name}</p>
                ` : `
                  <div class="aspect-[16/10] bg-brand-lightGray rounded flex items-center justify-center text-[11px] text-brand-muted">Not Selected</div>
                `}
                <button onclick="window.app.goToChapter(3)" class="text-[11px] text-brand-bronze font-semibold underline">Edit</button>
              </div>

              <!-- Kitchen -->
              <div class="bg-brand-offwhite p-3 rounded border border-brand-border space-y-2">
                <span class="text-[10px] font-bold tracking-wider text-brand-muted uppercase">04 Kitchen</span>
                ${selectedKit ? `
                  <div class="aspect-[16/10] bg-black rounded overflow-hidden">
                    <img src="${selectedKit.image_url}" alt="${selectedKit.style_name}" class="w-full h-full object-cover" />
                  </div>
                  <p class="text-xs font-serif font-bold text-brand-black truncate">${selectedKit.style_name}</p>
                ` : `
                  <div class="aspect-[16/10] bg-brand-lightGray rounded flex items-center justify-center text-[11px] text-brand-muted">Not Selected</div>
                `}
                <button onclick="window.app.goToChapter(4)" class="text-[11px] text-brand-bronze font-semibold underline">Edit</button>
              </div>

            </div>
          </div>

          <!-- Section-by-Section Audit Cards -->
          <div class="space-y-4">
            ${this.schema.chapters.map((ch, idx) => `
              <div class="bg-white p-5 rounded-lg border border-brand-border flex items-center justify-between shadow-luxury">
                <div class="space-y-1">
                  <div class="flex items-center space-x-2">
                    <span class="text-[10px] font-bold bg-brand-lightGray px-2 py-0.5 rounded text-brand-black uppercase">CHAPTER ${ch.number}</span>
                    <h4 class="font-serif text-sm sm:text-base font-bold text-brand-black">${ch.title}</h4>
                  </div>
                  <p class="text-xs text-brand-muted hidden sm:block">${ch.description}</p>
                </div>
                <button onclick="window.app.goToChapter(${idx})" class="px-4 py-2 text-xs font-bold tracking-wider uppercase border border-brand-border hover:border-brand-black bg-white hover:bg-brand-black hover:text-white transition-all rounded-sm flex-shrink-0 ml-4">
                  View / Edit
                </button>
              </div>
            `).join('')}
          </div>

          <!-- Final Submission Safeguard & Action -->
          <div class="bg-brand-charcoal text-white p-8 rounded-lg shadow-2xl text-center space-y-6">
            <div class="space-y-2 max-w-xl mx-auto">
              <h3 class="font-serif text-2xl font-bold">Ready to Submit Your Brief?</h3>
              <p class="text-xs text-gray-300 leading-relaxed">
                Once submitted, your complete responses and selected design references will be shared directly with the Shameer Associates design studio.
              </p>
            </div>

            <div class="flex flex-col sm:flex-row items-center justify-center gap-4">
              <button onclick="window.app.submitBrief()" class="w-full sm:w-auto px-12 py-4 bg-white hover:bg-brand-bronzeLight text-brand-black hover:text-white text-xs sm:text-sm font-bold tracking-[0.2em] uppercase rounded-sm shadow-xl transition-all flex items-center justify-center space-x-3">
                <i data-lucide="send" class="w-4 h-4"></i>
                <span>SUBMIT DESIGN QUESTIONNAIRE</span>
              </button>
            </div>
          </div>

        </div>
      `;
    }

    async submitBrief() {
      if (!this.sessionToken) return;
      try {
        const res = await fetch(`/api/session/${this.sessionToken}/submit`, {
          method: 'POST'
        });
        const data = await res.json();
        if (data.success) {
          this.sessionData.status = 'submitted';
          this.currentScreen = 'success';
          this.render();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      } catch (err) {
        console.error('Submission error:', err);
      }
    }

    // ========================================================
    // SCREEN 5: SUCCESS, PDF PREVIEW & CONSULTATION SCHEDULER
    // ========================================================
    renderSuccessScreen() {
      const answers = this.sessionData.answers || {};
      const clientName = answers.client_name || 'Client';

      return `
        <div class="animate-fade-in max-w-4xl mx-auto text-center py-6 sm:py-12 space-y-8 sm:space-y-12">
          
          <!-- Celebration Header -->
          <div class="space-y-4">
            <div class="w-16 h-16 bg-emerald-50 text-emerald-600 rounded-full flex items-center justify-center mx-auto border border-emerald-200">
              <i data-lucide="check-circle" class="w-8 h-8"></i>
            </div>
            <span class="text-xs font-bold tracking-[0.25em] text-brand-bronze uppercase">Design Brief Received</span>
            <h2 class="font-serif text-3xl sm:text-5xl font-bold text-brand-black">Thank You, ${clientName}</h2>
            <p class="text-xs sm:text-sm text-brand-slate max-w-xl mx-auto leading-relaxed">
              Your residential design brief has been saved and shared with the Shameer Associates architectural team.
            </p>
          </div>

          <!-- Design Brief Confirmation (Client PDF access removed — architect only) -->
          <div class="bg-white p-6 sm:p-8 rounded-lg shadow-luxury border border-brand-border max-w-2xl mx-auto space-y-4">
            <div class="flex items-center justify-between border-b border-brand-border/60 pb-3">
              <span class="text-xs font-bold tracking-wider text-brand-black uppercase">Design Brief Status</span>
              <span class="text-[11px] text-emerald-600 font-semibold">✓ Submitted to Studio</span>
            </div>
            <div class="flex items-start space-x-3 text-left">
              <div class="w-8 h-8 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-600 flex-shrink-0 mt-0.5">
                <i data-lucide="file-check" class="w-4 h-4"></i>
              </div>
              <p class="text-xs text-brand-slate leading-relaxed">
                Your complete residential design brief — including all lifestyle answers, family needs, space preferences, and selected reference imagery — has been securely delivered to the Shameer Associates studio. Our architectural team will review your brief in preparation for your consultation.
              </p>
            </div>
          </div>

          <!-- Consultation Booking Scheduler -->
          <div class="bg-white p-6 sm:p-8 rounded-lg shadow-luxury border border-brand-border max-w-2xl mx-auto text-left space-y-6">
            <div class="space-y-1">
              <span class="text-xs font-bold tracking-[0.2em] text-brand-bronze uppercase">Next Step</span>
              <h3 class="font-serif text-xl sm:text-2xl font-bold text-brand-black">Schedule Your Design Consultation</h3>
              <p class="text-xs text-brand-muted leading-relaxed">
                Meet with Shameer Associates to review your design brief, discuss concept ideas, and begin the architectural journey.
              </p>
            </div>

            <div id="consultation-form" class="space-y-4 pt-2">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-[11px] font-bold text-brand-black uppercase mb-1">Preferred Date</label>
                  <input type="date" id="consult-date" class="w-full p-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black" />
                </div>
                <div>
                  <label class="block text-[11px] font-bold text-brand-black uppercase mb-1">Preferred Time Slot</label>
                  <select id="consult-time" class="w-full p-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black">
                    <option value="10:00 AM – 11:30 AM">Morning (10:00 AM – 11:30 AM)</option>
                    <option value="02:00 PM – 03:30 PM">Afternoon (02:00 PM – 03:30 PM)</option>
                    <option value="04:30 PM – 06:00 PM">Evening (04:30 PM – 06:00 PM)</option>
                    <option value="07:00 PM – 08:30 PM">Late Evening / NRI Slot (07:00 PM – 08:30 PM)</option>
                  </select>
                </div>
              </div>

              <div>
                <label class="block text-[11px] font-bold text-brand-black uppercase mb-1">Meeting Mode</label>
                <select id="consult-mode" class="w-full p-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black">
                  <option value="In-person Studio Meeting (Kerala)">In-person Studio Meeting (Kerala)</option>
                  <option value="Virtual Video Consultation (Google Meet / Zoom)">Virtual Video Consultation (Google Meet / Zoom)</option>
                  <option value="Site Visit Consultation">Site Visit Consultation</option>
                </select>
              </div>

              <div>
                <label class="block text-[11px] font-bold text-brand-black uppercase mb-1">Additional Notes / Discussion Points</label>
                <textarea id="consult-notes" rows="2" placeholder="Any specific questions for the architect..." class="w-full p-2.5 bg-brand-offwhite border border-brand-border rounded text-xs text-brand-black leading-relaxed"></textarea>
              </div>

              <div id="consultation-status-msg" class="text-xs font-semibold hidden"></div>

              <button type="button" onclick="window.app.bookConsultation()" class="w-full py-3.5 bg-brand-black hover:bg-brand-bronze text-white text-xs font-bold tracking-widest uppercase rounded-sm shadow transition-colors flex items-center justify-center space-x-2">
                <i data-lucide="calendar" class="w-4 h-4"></i>
                <span>Confirm Consultation Booking</span>
              </button>
            </div>
          </div>

        </div>
      `;
    }

    async bookConsultation() {
      const date = document.getElementById('consult-date')?.value;
      const time = document.getElementById('consult-time')?.value;
      const mode = document.getElementById('consult-mode')?.value;
      const notes = document.getElementById('consult-notes')?.value;
      const statusMsg = document.getElementById('consultation-status-msg');

      if (!date) {
        alert('Please choose a preferred consultation date.');
        return;
      }

      try {
        const res = await fetch(`/api/session/${this.sessionToken}/consultation`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            date,
            time,
            meeting_type: mode,
            notes
          })
        });
        const data = await res.json();
        if (data.success) {
          if (statusMsg) {
            statusMsg.classList.remove('hidden', 'text-red-600');
            statusMsg.classList.add('text-emerald-600');
            statusMsg.textContent = '✓ Consultation booked successfully! The Shameer Associates team will reach out to confirm.';
          }
        }
      } catch (err) {
        console.error('Consultation booking error:', err);
      }
    }

    escapeHtml(str) {
      if (typeof str !== 'string') return '';
      return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }
  }

  // Instantiate application
  window.app = new ShameerApp();
})();
