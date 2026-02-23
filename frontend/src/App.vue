<template>
  <div id="app">
    <nav>
      <router-link to="/">Home</router-link>
      <router-link to="/library">Library</router-link>
    </nav>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
nav {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  border-bottom: 1px solid #eee;
}

nav a {
  text-decoration: none;
  color: #333;
  font-weight: 500;
}

nav a.router-link-active {
  color: #4285f4;
}

main {
  padding: 1rem;
}
</style>
