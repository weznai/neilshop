<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">🤝</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Collabs</h1>
        <p style="color:var(--gray)">Limited drops co-created with creators you love.</p>
      </div>
      <div class="grid grid-2">
        <div v-for="c in [
          ['@nailbedbynia', 'Nia x GLOWMAG', 'Chrome & glass collection', 'https://placehold.co/400x400/DDD6E8/552338?text=NIA+x+GM'],
          ['@thedailyglam', 'Daily Glam Capsule', 'Everyday neutrals, 6 shades', 'https://placehold.co/400x400/FBEBD4/8A6D3B?text=Daily+Glam'],
        ]" :key="c[1]" class="card" style="padding:0;overflow:hidden">
          <img :src="c[3]" :alt="c[1]" style="width:100%;aspect-ratio:1;object-fit:cover">
          <div style="padding:18px">
            <span class="tag tag-pending">{{ c[0] }}</span>
            <b style="display:block;font-family:var(--font-title);font-size:19px;margin:8px 0 4px">{{ c[1] }}</b>
            <div style="font-size:13px;color:var(--gray);margin-bottom:12px">{{ c[2] }}</div>
            <router-link to="/store" class="btn btn-secondary btn-sm">Shop the drop →</router-link>
          </div>
        </div>
      </div>
      <div class="card" style="padding:22px;margin-top:22px;text-align:center">
        <b>Want to collab?</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 12px">10k+ followers + a love for nails = let's talk.</p>
        <router-link to="/contact" class="btn btn-primary btn-sm">Apply via Contact</router-link>
      </div>
    </div>
  </section>
</template>
