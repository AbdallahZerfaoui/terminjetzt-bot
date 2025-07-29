# Makefile to build, run, and clean the TerminJetzt Heilbronn bot container

# Adjust these variables as needed

IMAGE_NAME := terminbot
CONTAINER_NAME := terminbot
DOCKERFILE := Dockerfile

.PHONY: build run clean

# Build the Docker image without affecting other images

build:
	docker build -f \$(DOCKERFILE) -t \$(IMAGE_NAME) .

# Run the container in detached mode, exposing port 80

# If a container with the same name exists, it will fail to start

run:
	docker run -d \
	--name $(CONTAINER_NAME) \
	--restart unless-stopped \
	-v $(PWD)/menu.yaml:/app/menu.yaml \
	-v $(PWD)/bot_main.py:/app/bot_main.py \
	$(IMAGE_NAME)

# Clean up the image and container created by this Makefile only

clean:
	docker rm -f \$(CONTAINER_NAME) 2>/dev/null || true
	docker rmi \$(IMAGE_NAME) 2>/dev/null || true
