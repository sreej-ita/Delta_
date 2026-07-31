FROM node:20-alpine

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm install

# Copy the rest of the frontend code
COPY . .

EXPOSE 5173

# --host 0.0.0.0 is required so the dev server is reachable from outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]